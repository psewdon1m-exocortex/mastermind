"""Versioned, disposable search text. Canonical Markdown is never rewritten."""
import math
import re
from collections import Counter
from itertools import pairwise

import yaml

VERSION = "search-content.v2"
STOP = frozenset(["the", "a", "an", "of", "on", "in", "and", "or", "to", "for", "from", "with", "this", "that", "is", "are", "by", "as", "at", "it", "be", "into", "these", "those", "и", "в", "во", "на", "для", "из", "по", "с", "со", "о", "об", "как", "что", "это", "или", "к", "от", "до", "не", "а", "но", "при", "этот", "эта", "эти", "свой", "также", "source", "facts", "about", "note", "summary", "material", "заметка", "заметки", "материал", "источник", "сведения", "связи", "признаки"])
STRUCTURAL = {"main", "key", "root", "pool", "template"}


def terms(text):
    return {w for w in re.findall(r"[^\W_]{2,64}", text.casefold().replace("ё", "е"))
            if w not in STOP and not w.isdigit() and not re.fullmatch(r"[a-f0-9]{16,}", w)}


def content(text, *, layout=False):
    """Preserve human labels and topical metadata; discard syntax and opaque identifiers."""
    topical = []
    technical_tags = set()
    front = re.match(r"\A\ufeff?---\r?\n([\s\S]*?)\r?\n(?:---|\.\.\.)(?:\r?\n|$)", text)
    if front:
        try:
            raw = front[1][:65536]
            if not any(isinstance(t, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)) for t in yaml.scan(raw)):
                data = yaml.safe_load(raw)
                if isinstance(data, dict):
                    for key in ("title", "description", "summary", "aliases", "alias", "topics", "tags"):
                        values = data.get(key, [])
                        for value in values[:32] if isinstance(values, list) else [values]:
                            if isinstance(value, str) and value.casefold().lstrip('#') not in STRUCTURAL:
                                topical.append(value[:1000])
                    for key in ("dataset", "kind", "id", "template"):
                        if isinstance(data.get(key), str):
                            technical_tags.add(data[key].casefold())
        except (yaml.YAMLError, ValueError, RecursionError):
            pass
        text = text[front.end():]
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    text = re.sub(r"(?m)^\s*(?:```|~~~).*?$", "", text)
    # External service references and URLs are identities, not semantic descriptions.
    text = re.sub(r"@(?:saturn|chronos):\s*[^\s]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"!?\[\[([^\]\n]+)\]\]", lambda m: m[1].split('|')[-1].split('#')[0].rsplit('/', 1)[-1].removesuffix('.md'), text)
    text = re.sub(r"!?\[([^\]\n]*)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"(?:https?://|obsidian://)\S+", "", text)
    text = re.sub(r"(?<!\w)#([\w/-]+)", lambda m: "" if m[1].casefold() in STRUCTURAL | technical_tags else m[1], text)
    text = re.sub(r"(?m)^[ \t]*(?:[-*+][ \t]+|>[ \t]*)", "", text)
    if not layout:
        text = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]+", "", text)
    text = re.sub(r"[\[\]`*_]", "", text)
    if layout:
        return re.sub(r'\n{3,}', '\n\n', '\n'.join(line.strip() for line in [*topical, *text.splitlines()])).strip()
    return "\n".join(line.strip() for line in [*topical, *text.splitlines()] if line.strip())


def sentences(text):
    return [part.strip() for part in re.split(r"\n+|(?<=[.!?])\s+", text) if part.strip()]


def template_signature(text):
    return re.sub(r'«[^»]+»|"[^"\n]+"', '<label>', text.casefold())


def evidence(text, *, layout=False):
    """Unfilled fields and headings of empty sections are structure, not facts.

    Applied to every document, including ordinary notes with a partial template.
    The filename/title can still be used as evidence by the caller.
    """
    text = re.sub(r'\{\{[^{}\n]*\}\}', '', text)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if re.match(r'^\s*#{2,6}\s', line):
            end = index+1
            while end < len(lines) and not re.match(r'^\s*#{1,6}\s', lines[end]):
                end += 1
            if not terms(content('\n'.join(lines[index+1:end]))):
                lines[index] = ''
    return content('\n'.join(lines), layout=layout)


def prepare(text):
    """One deterministic representation for documents and queries, with sections.

    Offsets address prepared text, not canonical Markdown. Source section ranges
    identify the original Markdown under its SHA; cleanup never rewrites a note.
    """
    from markdown_it import MarkdownIt
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1]+len(line))
    headings = []
    for token in MarkdownIt('commonmark').parse(text):
        if token.type == 'heading_open' and token.map:
            a, b = token.map
            headings.append((content(''.join(lines[a:b])), offsets[a]))
    result, sections, stack = '', [], []
    current = {'start': 0, 'heading': '', 'source_start': 0}
    cursor = 0
    for line in evidence(text, layout=True).splitlines(keepends=True):
        match = re.match(r'^(#{1,6})\s+(.+)', line)
        source_start = next((position for name, position in headings if position >= cursor and
                             match and name == match[2].strip()), None)
        # A code sample may contain '# heading'. Only actual Markdown heading
        # tokens establish section boundaries; preserve its text as body evidence.
        if match and source_start is None:
            line = match[2].strip()+'\n'
            match = None
        if match:
            if len(result) > current['start']:
                sections.append({**current, 'end': len(result)})
            level, label = len(match[1]), match[2].strip()
            stack = [(depth, value) for depth, value in stack if depth < level]+[(level, label)]
            cursor = source_start+1
            current = {'start': len(result), 'heading': ' / '.join(v for _, v in stack)[:800],
                       'source_start': source_start}
            line = label+'\n'
        result += line
    result = result.rstrip()
    if len(result) > current['start']:
        sections.append({**current, 'end': len(result)})
    for i, section in enumerate(sections):
        section['source_end'] = sections[i+1]['source_start'] if i+1 < len(sections) else len(text)
    return {'text': result, 'sections': sections, 'version': VERSION}


def chunk_text(text, span):
    body = text[span['start']:span['end']]
    heading = span.get('heading', '')
    return (heading+'\n'+body) if heading and not body.startswith(heading) else body


class Corpus:
    """Bounded, scope-local statistics; private notes never contribute query expansion."""
    def __init__(self, documents):
        self.documents = documents
        self.count = max(1, len(documents))
        self.frequency = Counter(term for text in documents.values() for term in terms(text))
        # Copies of the same content are one observation of a template, not
        # independent evidence that their shared subject is boilerplate.
        sequences = [[template_signature(block) for block in sentences(text)]
                     for text in {evidence(raw) for raw in documents.values()}]
        threshold = max(3, math.ceil(self.count*.08))
        blocks = Counter(block for sequence in sequences for block in set(sequence)
                         if len(terms(block)) >= 3 and len(block) >= 25)
        self.boilerplate = {block for block, count in blocks.items() if count >= threshold}
        # Short headings/captions alone are ambiguous (e.g. "Energy"). Learn
        # repeated scaffolding from adjacent blocks, not a vocabulary blacklist.
        # This also recognizes a heading followed by an external-resource label
        # after its opaque ID is removed. A lone shared topical heading survives.
        pairs = Counter(pair for sequence in sequences for pair in set(pairwise(sequence))
                        if len(terms(' '.join(pair))) >= 3 and len(' '.join(pair)) >= 25)
        for pair, count in pairs.items():
            if count >= threshold:
                self.boilerplate.update(pair)
        cleaned = [self.clean(text) for text in documents.values()]
        self.frequency = Counter(term for text in cleaned for term in terms(text))

    def clean(self, text):
        return '\n'.join(s for s in sentences(evidence(text)) if terms(s) and template_signature(s) not in self.boilerplate)

    def weight(self, term):
        # Frequency softens evidence; a homogeneous Vault may legitimately use
        # the same topic everywhere. Frequency alone must never disable it.
        frequency = self.frequency[term]
        return math.log(1+(self.count+.5)/(frequency+.5))

    def overlap(self, source, target):
        common = terms(source) & terms(target)
        useful = sorted((t for t in common if self.weight(t) > 0), key=lambda t: (-self.weight(t), t))
        denominator = min(sum(self.weight(t) for t in terms(source)), sum(self.weight(t) for t in terms(target)))
        score = sum(self.weight(t) for t in useful)/max(1, denominator)
        return score, useful
