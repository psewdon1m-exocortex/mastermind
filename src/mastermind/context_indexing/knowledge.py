"""Content evidence for knowledge lookup, independent of Crusher parent eligibility."""
import json
import math
import re
import statistics

from ..errors import DomainError
from ..references import parse
from ..search_content import Corpus, content, sentences, terms


class Knowledge:
    def __init__(self, state, graph, allowed):
        self.state, self.graph, self.allowed = state, graph, allowed
        rows = state.rows("SELECT f.path,substr(f.body,1,12000) AS body FROM note_fts f JOIN notes n ON n.path=f.path "
                          "WHERE f.path IN (SELECT value FROM json_each(?)) ORDER BY n.name_key LIMIT 256",
                          (json.dumps(sorted(allowed)),))
        self.raw = {r['path']: r['body'] for r in rows}
        self.corpus = Corpus(self.raw)
        self.documents = {path: self.corpus.clean(text) for path, text in self.corpus.documents.items()}
        self.names = {n['name_key']: n['name'] for n in graph.notes.values() if n['path'] in allowed}
        self.paths = {n['name_key']: p for p, n in graph.notes.items() if p in allowed}
        self.links, self.context = set(), []

    def document(self, path):
        if path not in self.documents:
            row = self.state.one("SELECT substr(body,1,12000) AS body FROM note_fts WHERE path=?", (path,))
            self.raw[path] = row['body'] if row else ''
            self.documents[path] = self.corpus.clean(row['body']) if row else ''
        return self.documents[path]

    def prepare(self, subject):
        raw = subject.get('source_body', '\n'.join(subject.get('raw_chunks', [])) or subject['text'])
        # The authorized editor buffer participates in repetition detection, but
        # remains excluded from candidates and graph expansion.
        self.corpus = Corpus({**{p: t for p, t in self.corpus.documents.items() if p != '@query'},
                              '@query': raw})
        self.documents = {path: self.corpus.clean(text) for path, text in self.corpus.documents.items() if path != '@query'}
        self.context = []
        self.links = {self.paths[r.target] for r in parse(raw, self.names)
                      if r.kind == 'internal' and r.exists and r.target in self.paths}
        self.own = self.corpus.clean(raw)
        self.descriptive = self.has_description(raw)
        self.title = subject.get('source_title', '')
        self.query = self.title + '\n' + self.own
        focus = self.corpus.clean(subject.get('source_focus', ''))
        self.focus = focus
        # A sparse outline gains bounded context from actual links, never from folders.
        # Keep snippets separate: a mixed-topic outline must not become a single topic claim.
        if len(terms(self.own)) <= 28 and len(self.links) >= 2:
            for path in sorted(self.links, key=lambda p: self.graph.notes[p]['name_key'])[:4]:
                text = self.document(path)
                if text:
                    self.context.append({'path': path, 'sha256': self.graph.notes[path]['sha'], 'text': text[:600]})
        chunks = [self.corpus.clean(s) for s in subject.get('raw_chunks', [])]
        chunks = [s[:1600] for s in chunks if s.strip()]
        capacity = 8-len(self.context)
        if len(chunks) > capacity:
            chunks = [chunks[i*(len(chunks)-1)//(capacity-1)] for i in range(capacity)]
        chunks += [v['text'] for v in self.context]
        query = self.title + '\n' + (focus or self.own[:1600])
        if not query.strip():
            query = self.corpus.clean(subject['text']) or ' '
        return {**subject, 'text': query.encode()[:4096].decode(errors='ignore'), 'raw_chunks': chunks,
                'context_sources': [{k: v[k] for k in ('path', 'sha256')} for v in self.context]}

    def has_description(self, raw):
        # A list of titles/links says what a note points at, but does not assert
        # semantic similarity to every other outline. All paths and note roles
        # follow this evidence rule, and remain eligible through explicit topics.
        spans = [(r.start, r.end) for r in parse(raw, self.names)]
        # A short self-contained topic/query is still meaningful. The stricter
        # prose requirement concerns navigational outlines, not text length or
        # a special class of notes.
        standalone = not spans and bool(terms(self.corpus.clean(raw)))
        for start, end in sorted(spans, reverse=True):
            raw = raw[:start]+' '+raw[end:]
        raw = re.sub(r'(?m)^\s*#{1,6}\s+.*$', '', raw)
        return standalone or any(len(terms(p)) >= 5 for p in sentences(self.corpus.clean(raw)))

    def rank(self, items):
        vectors = [i['features'].get('vector', 0) for i in items if 'vector' in i['features']]
        # The lower half estimates unrelated background even in a small Vault
        # where several equally relevant peers occupy the upper half.
        background = statistics.median(sorted(vectors)[:max(1, len(vectors)//2)]) if vectors else 0
        for item in items:
            document = self.document(item['path'])
            lexical, common = self.corpus.overlap(self.query, document)
            title, title_terms = self.corpus.overlap(self.query, item['title'])
            title = title if title_terms else 0
            semantic = max(0, min(1, (item['features'].get('vector', 0)-.7)/.3))
            # Word rarity and independent title evidence matter more than boilerplate cosine.
            item['score'] = round(.45*lexical + .25*title + .30*semantic, 6)
            item['features'].update(lexical=lexical, title_match=title, topical_terms=common[:8])
            # Cosine is not a probability. Semantic-only matches need contrast with
            # the scoped background, while explicit topical words can work offline.
            topical = lexical >= .14 and len(common) >= 2 or title >= .75 and bool(title_terms)
            descriptive = self.descriptive and self.has_description(self.raw.get(item['path'], ''))
            semantic_only = descriptive and item['features'].get('vector', 0) >= .80 \
                and item['features'].get('vector', 0)-background >= .055
            corroborated = lexical >= .05 and len(common) >= 2 and item['features'].get('vector', 0) >= .82 \
                and item['features'].get('vector', 0)-background >= .025
            item['features']['supported'] = bool(topical or semantic_only or corroborated)
            item['relation'] = 'linked' if item['path'] in self.links else 'similar'
            item['reason'] = ('Linked from this note' if item['relation'] == 'linked' else
                              'Shared topics: ' + ', '.join(common[:4]) if common else
                              'Similar to linked note context' if self.context else 'Similar subject matter')
            navigation = set()
            for line in self.raw.get(item['path'], '').splitlines():
                prose = re.sub(r'!?\[\[[^\]\n]+\]\]|(?<!\w)@[^\n]+', '', line)
                if len(prose.strip()) < len(line.strip())*.5:
                    navigation.update(sentences(content(line)))
            passages = [p for p in sentences(document) if p not in navigation and p != item['title'] and len(terms(p)) >= 5]
            passages = passages or sentences(document)
            passage = max(passages, key=lambda p: (self.corpus.overlap(self.query, p)[0], len(p)), default='')
            item['excerpt'] = passage[:320]
            item['context_sources'] = [{k: v[k] for k in ('path', 'sha256')} for v in self.context]
        return sorted(items, key=lambda v: (-v['score'], self.graph.notes[v['path']]['name_key']))

    def verify(self, items, semantic, deadline):
        # Keep a lower-ranked background sample as well as likely matches.
        # Candidates outside this bounded pass can still qualify lexically, but
        # their unverified retrieval cosine cannot authorize a suggestion.
        ordered = self.rank(items)
        selected = ordered if len(ordered) <= 64 else ordered[:48]+ordered[-16:]
        for item in items:
            if 'vector' in item['features']:
                item['features']['retrieval_vector'] = item['features'].pop('vector')
        if not semantic or not hasattr(semantic, 'compare'):
            return False
        # Score filenames separately; prepending an arbitrary filename to prose
        # can dilute cross-language meaning or duplicate its Markdown heading.
        evidence = [(item, (self.document(item['path']) or item['title'])[:1600]) for item in selected]
        # Linked context helps candidate discovery, but the final semantic
        # claim must match the source itself, not just one of its neighbors.
        source = self.own or self.title
        count = min(4, max(1, math.ceil(len(source)/1600)))
        queries = [source[i*max(0, len(source)-1600)//max(1, count-1):][:1600] for i in range(count)]
        if self.focus:
            queries.append(self.focus[:1600])
        queries = list(dict.fromkeys(queries))
        queries = [q for q in queries if q.strip()]
        if not queries or not evidence:
            return True
        try:
            scores = semantic.compare(queries, [text for _, text in evidence], deadline=deadline)
        except DomainError:
            return False
        for (item, _), score in zip(evidence, scores, strict=True):
            item['features']['vector'] = round(score, 6)
        return True
