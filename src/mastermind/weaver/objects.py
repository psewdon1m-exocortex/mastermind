"""Bounded graph traversal including referenced resources; never fetches remote bodies."""
from collections import deque
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from ..errors import DomainError
from ..fs import resolve, sha_bytes
from ..references import WIKI, masked
from .graph import Graph


def attachments(vault, source, scope):
    raw = vault.read(source)
    visible = masked(raw)
    targets = [m[2].split('|', 1)[0].split('#', 1)[0] for m in WIKI.finditer(visible)]
    for block in MarkdownIt('commonmark').parse(raw):
        for token in block.children or ():
            if token.type in {'image', 'link_open'}:
                targets.append(token.attrGet('src') or token.attrGet('href') or '')
    seen = set()
    for target in targets[:400]:
        try:
            remote = bool(urlsplit(target).scheme) or target.startswith('//')
        except ValueError:
            continue
        if remote:
            continue
        target = unquote(target.split('#', 1)[0])
        if not PurePosixPath(target).suffix or target.lower().endswith('.md'):
            continue
        for candidate in (target, str(PurePosixPath(source).parent/target)):
            if candidate in seen or not scope.permits(candidate):
                continue
            try:
                file = resolve(vault.config.vault, candidate)
                if not file.is_file():
                    continue
                stat = file.stat()
            except (DomainError, OSError):
                continue
            seen.add(candidate)
            yield {'id': 'attachment:'+candidate, 'kind': 'attachment', 'path': candidate, 'size': stat.st_size}
            break


def walk(vault, request):
    if request.direction not in {'incoming', 'outgoing', 'both'} or type(request.depth) is not int \
            or not 0 <= request.depth <= 4 or type(request.limit) is not int or not 1 <= request.limit <= 200:
        raise DomainError('INVALID_WALK', 'Use a graph depth of 0–4 and 1–200 objects.', 422)
    graph = Graph(vault, request.scope)
    if request.path not in graph.notes:
        raise DomainError('NOT_FOUND', 'The starting note is outside the available graph.', 404)
    nodes, links, queue, visited = [], [], deque([(request.path, 0)]), {request.path}
    truncated = False
    while queue:
        path, depth = queue.popleft()
        note = graph.notes[path]
        nodes.append({'id': path, 'kind': 'note', 'title': note['name'], 'sha256': note['sha']})
        if depth >= request.depth:
            continue
        outgoing = graph.outgoing[path] if request.direction != 'incoming' else set()
        incoming = graph.incoming[path] if request.direction != 'outgoing' else set()
        for target in sorted(outgoing | incoming):
            if target not in visited:
                if len(visited) >= request.limit:
                    truncated = True
                    continue
                visited.add(target)
                queue.append((target, depth+1))
            edge = {'source': path if target in outgoing else target,
                    'target': target if target in outgoing else path, 'kind': 'internal'}
            if edge not in links:
                links.append(edge)
        if request.direction == 'incoming':
            continue
        # Source revision is rechecked after traversal. Metadata only; binary
        # attachment bytes and remote-resource bodies never enter this walk.
        for attachment in attachments(vault, path, request.scope):
            if attachment['id'] not in visited:
                if len(visited) >= request.limit:
                    truncated = True
                    continue
                visited.add(attachment['id'])
                nodes.append(attachment)
            links.append({'source': path, 'target': attachment['id'], 'kind': 'attachment'})
        for edge in vault.state.rows('SELECT kind,target_key,broken FROM edges WHERE source=? '
                                     'AND kind IN (\'saturn\',\'chronos\') ORDER BY kind,target_key LIMIT 201', (path,)):
            identity = edge['kind']+':'+edge['target_key']
            if identity not in visited:
                if len(visited) >= request.limit:
                    truncated = True
                    continue
                visited.add(identity)
                nodes.append({'id': identity, 'kind': edge['kind'], 'reference': edge['target_key'],
                              'availability': 'unverified'})
            links.append({'source': path, 'target': identity, 'kind': edge['kind']})
    for node in nodes:
        if node['kind'] == 'note' and sha_bytes(vault.read(node['id']).encode()) != node['sha256']:
            raise DomainError('GRAPH_CHANGED', 'The graph changed during traversal; retry the work order.', 409)
    return {'schema': 'weaver.walk.v1', 'snapshot_id': graph.sha, 'nodes': nodes, 'edges': links,
            'truncated': truncated}
