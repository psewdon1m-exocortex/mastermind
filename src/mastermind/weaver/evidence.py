"""Bounded, versioned evidence shared by typed Weaver work-order results.

Source identity is path-bound (the Vault has no persistent note UUID). Prepared
offsets are Unicode codepoints, not byte offsets or Markdown editing positions.
"""
import re
import time
from itertools import pairwise

from ..errors import DomainError
from ..fs import sha_bytes
from ..search_content import VERSION, Corpus, prepare, terms


def note_id(path):
    return 'note:' + path


def dependencies(item):
    return ({p for chain in item.get('graph_paths', []) for p in chain} |
            {v['path'] for v in item.get('context_sources', [])} | set(item.get('profile_sources', {})))


def diagnostics(result, *, returned=None):
    selected = None if returned is None else {i['path'] for i in returned}
    stale = set(result.get('stale_paths', []))
    entries = []
    for rank, item in enumerate(result.get('diagnostic_candidates', result.get('results', []))[:300], 1):
        features = item.get('features', {})
        accepted = features.get('supported', True) and item['path'] not in result.get('negated_entities', [])
        stage = ('freshness' if item['path'] in stale else 'verification' if not accepted else
                 'limit' if selected is not None and item['path'] not in selected else 'returned')
        reason = ('SOURCE_CHANGED' if stage == 'freshness' else 'EXCLUDED_TOPIC' if item['path'] in
                  result.get('negated_entities', []) else 'RESULT_LIMIT' if stage == 'limit' else
                  features.get('acceptance_reason', 'RETRIEVED'))
        entries.append({'id': note_id(item['path']), 'path': item['path'], 'sha256': item.get('sha256'),
                        'discovery': sorted(item.get('strategies', {})),
                        'candidate_rank': item.get('rank_before_verification', rank), 'final_rank': rank,
                        'rank_score': item.get('score'),
                        'signals': {k: features[k] for k in ('lexical', 'title_match', 'vector', 'retrieval_vector',
                                    'semantic_background', 'semantic_contrast') if k in features},
                        'verification': features.get('verification', 'not_required'),
                        'stage': stage, 'reason': reason})
    return {'schema': 'weaver.diagnostics.v1', 'candidate_limit': 300,
            'counts': {**{k: sum(e['stage'] == k for e in entries) for k in
                        ('returned', 'verification', 'freshness', 'limit')}, 'candidates': len(entries)},
            'channels': result.get('channels', {}), 'candidates': entries,
            'limited_channels': result.get('limited_channels', []),
            'coverage_limited': bool(result.get('truncated') or result.get('degraded') or result.get('limited_channels'))}


def completeness(result):
    reasons = sorted(set(result.get('missing_strategies', [])) |
                     ({'SOURCE_CHANGED'} if result.get('stale_evidence') else set()) |
                     ({'SEARCH_LIMIT'} if result.get('truncated') or result.get('limited_channels') else set()))
    return {'state': 'partial' if reasons or result.get('degraded') else 'complete', 'reasons': reasons,
            'vector_index': result.get('vector_index', {'state': 'not_requested'}),
            'freshness': 'changed' if result.get('stale_evidence') else 'checked'}


def selected_diagnostics(result, items, evidence=None):
    value = result.get('diagnostics') or diagnostics(result)
    paths = {v['path'] for v in items}
    stale = set((evidence or {}).get('stale_paths', []))
    omitted = set((evidence or {}).get('omitted_paths', []))
    entries = [{**v, **({'stage': 'freshness', 'reason': 'SOURCE_CHANGED'} if v['path'] in stale else
                {'stage': 'evidence', 'reason': 'EVIDENCE_DEADLINE'} if v['path'] in omitted else
                {'stage': 'limit', 'reason': 'RESULT_LIMIT'}
                if v['stage'] == 'returned' and v['path'] not in paths else {})}
               for v in value['candidates']]
    return {**value, 'candidates': entries, 'counts': {**value['counts'],
        **{k: sum(e['stage'] == k for e in entries) for k in ('returned', 'limit', 'freshness', 'evidence')}}}


def _spans(prepared, item, query):
    """Prefer the verified passage, then the exact retrieved chunk receipt."""
    text, sections = prepared['text'], prepared['sections']
    excerpt = item.get('verified_excerpt', '')
    ranked = []
    for part in item.get('passages', []):
        a, b = part.get('start'), part.get('end')
        if type(a) is int and type(b) is int and 0 <= a < b <= len(text):
            matching = excerpt and (excerpt in text[a:b] or Corpus({'x': part['text']}).clean(part['text']) == excerpt)
            ranked.append((0 if matching else 1, -part.get('score', 0), a, b, part.get('chunk_id')))
    if excerpt:
        start = text.find(excerpt)
        if start >= 0:
            ranked.append((-1, 0, start, start+len(excerpt), None))
    if not ranked:
        # Lexical/name matches still receive real coordinates, even offline.
        for section in sections:
            a, b = section['start'], section['end']
            for match in re.finditer(r'[^\n]+(?:\n(?!\n)[^\n]+)*', text[a:b]):
                start, end = a+match.start(), a+match.end()
                score = len(terms(query) & terms(match[0]))
                ranked.append((0, -score, start, end, None))
    result = []
    for _, _, a, b, chunk in sorted(ranked):
        if any(a < old[1] and b > old[0] for old in result):
            continue
        result.append((a, b, chunk))
        if len(result) == 2:
            break
    return result


def _context(prepared, start, end, mode):
    text, sections = prepared['text'], prepared['sections']
    section = next((s for s in sections if s['start'] <= start < s['end']), None)
    if not section or mode == 'none':
        return []
    paragraphs = [(m.start()+section['start'], m.end()+section['start'])
                  for m in re.finditer(r'[^\n]+(?:\n(?!\n)[^\n]+)*', text[section['start']:section['end']])]
    before = [(a, b, 'adjacent_paragraph') for a, b in paragraphs if b <= start]
    after = [(a, b, 'adjacent_paragraph') for a, b in paragraphs if a >= end]
    result = before[-1:] + after[:1]
    if mode == 'section' and section['heading']:
        # Include ancestor introduction only, not all sibling/descendant sections.
        ancestors = [s for s in sections if s['end'] <= section['start'] and s['heading'] and
                     section['heading'].startswith(s['heading']+' / ')]
        if ancestors:
            parent = ancestors[-1]
            result.append((parent['start'], parent['end'], 'parent_section'))
    return result


def packet(result, graph, items, *, query='', context='none', budget=32768, deadline=None):
    if context not in {'none', 'adjacent', 'section'} or type(budget) is not int or not 0 <= budget <= 65536:
        raise DomainError('CONTEXT_BUDGET', 'Use a context mode and a byte budget from 0 to 65536.', 422)
    status = completeness(result)
    output = {'schema': 'weaver.evidence.v1', 'task': result.get('task'),
              'snapshot_id': result.get('snapshot_id'), 'score_semantics': 'ranking_not_probability',
              'identity_semantics': 'path_bound', 'completeness': status, 'sources': [], 'stale_paths': [], 'omitted_paths': [],
              'context': {'mode': context, 'budget_bytes': budget, 'used_bytes': 0, 'truncated': False}}
    if graph is None:
        return output
    if len(items) > 200:
        status['state'] = 'partial'
        status['reasons'].append('EVIDENCE_SOURCE_LIMIT')
        items = items[:200]
    for ordinal, item in enumerate(items[:200]):
        if deadline is not None and time.monotonic() >= deadline:
            status['state'] = 'partial'
            status['reasons'].append('EVIDENCE_DEADLINE')
            output['omitted_paths'].extend(i['path'] for i in items[ordinal:])
            break
        path, expected = item['path'], item['sha256']
        if path not in graph.notes:
            continue
        try:
            raw = graph.vault.read(path)
            if sha_bytes(raw.encode()) != expected:
                raise DomainError('SOURCE_CHANGED', 'Evidence changed.', 409)
            for target in dependencies(item):
                if target not in graph.notes or sha_bytes(graph.vault.read(target).encode()) != graph.notes[target]['sha']:
                    raise DomainError('SOURCE_CHANGED', 'Evidence changed.', 409)
        except DomainError:
            status.update(state='partial', freshness='changed')
            status['reasons'].append('SOURCE_CHANGED')
            output['stale_paths'].append(path)
            continue
        prepared = prepare(raw) if budget else {'text': '', 'sections': []}
        source = {'id': note_id(path), 'path': path, 'sha256': expected, 'title': item.get('title'),
                  'rank_score': item.get('score'), 'acceptance': item.get('features', {}).get('acceptance'),
                  'reason': item.get('reason'), 'reason_code': item.get('features', {}).get('acceptance_reason'),
                  'discovery': sorted(item.get('strategies', {})), 'fragments': [],
                  'query_parts': [p['id'] for p in result.get('coverage', []) if path in p['paths']],
                  'graph_paths': [[{'id': note_id(p), 'path': p, 'sha256': graph.notes[p]['sha']}
                                   for p in chain] for chain in item.get('graph_paths', [])],
                  'graph_edges': list({(a, b): {'source': note_id(a), 'target': note_id(b)}
                    for chain in item.get('graph_paths', []) for left, right in pairwise(chain)
                    for a, b in ((left, right), (right, left)) if b in graph.outgoing[a]}.values()),
                  'graph_context_sources': item.get('context_sources', []),
                  'profile_sources': [{'id': note_id(p), 'path': p, 'sha256': sha}
                                      for p, sha in item.get('profile_sources', {}).items()],
                  'freshness': 'checked', 'representation': VERSION}
        spans = _spans(prepared, item, query)
        wanted = [(a, b, 'match', chunk) for a, b, chunk in spans]
        for a, b, _ in spans:
            wanted += [(left, right, kind, None) for left, right, kind in _context(prepared, a, b, context)]
        seen = []
        for a, b, kind, chunk in wanted:
            if any(a < right and b > left for left, right in seen):
                continue
            available = min(3200 if kind == 'match' else 1600, budget-output['context']['used_bytes'])
            text = prepared['text'][a:b].encode()[:max(0, available)].decode(errors='ignore')
            if len(text) < b-a:
                output['context']['truncated'] = True
            if not text:
                continue
            b = a+len(text)
            section = next((s for s in prepared['sections'] if s['start'] <= a < s['end']), {})
            source['fragments'].append({'kind': kind, 'text': text, 'heading': section.get('heading', ''),
                'coordinates': {'space': 'prepared', 'unit': 'unicode_codepoint', 'start': a, 'end': b},
                'source_section': {'space': 'markdown', 'unit': 'unicode_codepoint',
                                   'start': section.get('source_start', 0), 'end': section.get('source_end', len(raw))},
                'chunk_id': chunk})
            seen.append((a, b))
            output['context']['used_bytes'] += len(text.encode())
        output['sources'].append(source)
    # Validate again at the return boundary: formatting a large excerpt may
    # overlap an editor save, including a save to a graph evidence dependency.
    required = {i['path'] for i in items} | {p for i in items for p in dependencies(i)}
    hashes = {p: graph.notes[p]['sha'] for p in required if p in graph.notes}
    changed, unchecked = set(), set()
    for path, expected in hashes.items():
        if deadline is not None and time.monotonic() >= deadline:
            unchecked.add(path)
            continue
        try:
            if sha_bytes(graph.vault.read(path).encode()) != expected:
                changed.add(path)
        except DomainError:
            changed.add(path)
    if changed:
        affected = {i['path'] for i in items if changed & ({i['path']} | dependencies(i))}
        output['stale_paths'] = sorted(set(output['stale_paths']) | affected)
        output['sources'] = [s for s in output['sources'] if s['path'] not in affected]
        status.update(state='partial', freshness='changed')
        status['reasons'].append('SOURCE_CHANGED')
    if unchecked:
        omitted = {i['path'] for i in items if unchecked & ({i['path']} | dependencies(i))}
        output['omitted_paths'] = sorted(set(output['omitted_paths']) | omitted)
        output['sources'] = [s for s in output['sources'] if s['path'] not in omitted]
        status['state'] = 'partial'
        status['reasons'].append('EVIDENCE_DEADLINE')
    output['context']['used_bytes'] = sum(len(f['text'].encode()) for s in output['sources'] for f in s['fragments'])
    status['reasons'] = sorted(set(status['reasons']))
    return output
