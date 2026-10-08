"""Small deterministic Lookup plan; no inference for interactive Similar."""
import re

from ..errors import DomainError


def directions(query, mode='auto'):
    if mode not in {'auto', 'single'}:
        raise DomainError('LOOKUP_PLAN', 'Choose auto or single search planning.', 422)
    if mode == 'single':
        return []
    if re.match(r'^(?:как|почему|откуда|зачем|когда|где|какой|какие|how|why|what|when|where|which)\b',
                query.strip(), flags=re.IGNORECASE):
        # Punctuation inside a factual question is not a list of search tasks.
        return []
    # Split explicit lists only. Do not reinterpret a simple conjunction such
    # as "strength and stiffness" as two unrelated retrieval assignments.
    text = re.sub(r'^(?:найди|покажи|ищи|find|search|look\s+for)\s+', '', query.strip(), flags=re.IGNORECASE)
    text = re.sub(r'^(?:материалы|информацию|заметки|materials|information|notes)\s+(?:про|о|об|about|on)\s+', '', text, flags=re.IGNORECASE)
    if not re.search(r'[,;\n]', text):
        return []
    parts = re.split(r'[,;\n]+|\s+(?:и|and)\s+', text, flags=re.IGNORECASE)
    parts = list(dict.fromkeys(p.strip(' .?!') for p in parts if p.strip(' .?!')))
    if not 2 <= len(parts) <= 4 or any(len(p) < 3 or len(p.encode()) > 1000 for p in parts):
        return []
    return parts[:2]+['; '.join(parts[2:])] if len(parts) == 4 else parts


def valid_refinement(original, refined):
    """Model suggestions may add plain search terms, never request fields."""
    if not isinstance(refined, dict) or set(refined)-set(original) or not isinstance(refined.get('text'), str):
        return False
    if any(refined.get(k) != v for k, v in original.items() if k != 'text'):
        return False
    text = refined['text']
    if not text.startswith(original['text']+'\n') or len(text.encode()) > 4096:
        return False
    suffix = text[len(original['text']):].strip()
    return bool(suffix) and not re.search(r'[@<>\[\]{}\\/:\x00-\x1f]', suffix)


def union(first, second):
    """Keep per-direction judgments, not a diluted re-score of a compound query."""
    values = {i['path']: i for i in first['results']}
    for item in second['results']:
        old = values.get(item['path'])
        if old is None:
            values[item['path']] = item
            continue
        priority = lambda v: (v['features'].get('supported', False), v['score'])
        winner, other = (item, old) if priority(item) > priority(old) else (old, item)
        winner['strategies'] = {k: min(old['strategies'].get(k, 999), item['strategies'].get(k, 999))
                                for k in old['strategies'].keys() | item['strategies'].keys()}
        winner['graph_paths'] = list({tuple(v): v for v in [*winner.get('graph_paths', []), *other.get('graph_paths', [])]}.values())
        winner['passages'] = list({(v.get('start'), v.get('end'), v.get('text')): v for v in
            [*winner.get('passages', []), *other.get('passages', [])]}.values())[:8]
        values[item['path']] = winner
    return {**first, 'results': sorted(values.values(), key=lambda v: (-v['score'], v['path']))[:300],
            'channels': {k: max(first['channels'].get(k, 0), second['channels'].get(k, 0))
                         for k in first['channels'].keys() | second['channels'].keys()},
            'missing_strategies': sorted(set(first['missing_strategies']) | set(second['missing_strategies'])),
            'limited_channels': sorted(set(first.get('limited_channels', [])) | set(second.get('limited_channels', []))),
            'degraded': first['degraded'] or second['degraded'],
            'truncated': first['truncated'] or second['truncated'] or len(values) > 300}
