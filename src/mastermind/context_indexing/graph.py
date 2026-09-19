"""Immutable graph snapshots and a consumer-specific structural projection."""
import json
from collections import defaultdict, deque
from dataclasses import dataclass

from ..errors import DomainError
from ..fs import sha_bytes


def digest(value):
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


@dataclass(frozen=True)
class Scope:
    principal: str
    paths: frozenset[str] | None = None

    def permits(self, path):
        return self.principal in {"owner", "crusher"} and (self.paths is None or path in self.paths)


class Graph:
    def __init__(self, vault, scope, *, refresh=True):
        if scope.principal not in {"owner", "crusher"}:
            raise DomainError("FORBIDDEN", "Context-indexing requires an authorized service or owner scope.", 403)
        self.scope = scope
        with vault.coordinator.lock:
            if refresh:
                vault.index()
            self.notes = {row["path"]: {**row, "tags": json.loads(row["tags"])}
                          for row in vault.state.rows("SELECT * FROM notes") if scope.permits(row["path"])}
            names = {note["name_key"]: path for path, note in self.notes.items()}
            self.outgoing, self.incoming = defaultdict(set), defaultdict(set)
            for edge in vault.state.rows("SELECT source,target_key FROM edges WHERE kind='internal' AND broken=0"):
                target = names.get(edge["target_key"])
                if edge["source"] in self.notes and target:
                    self.outgoing[edge["source"]].add(target)
                    self.incoming[target].add(edge["source"])
            self.root = vault.state.setting("crusher_root", "root.md")
            self.generation = vault.state.one("SELECT value FROM metadata WHERE key='generation'")["value"]
        self.sha = digest([(p, n["sha"]) for p, n in sorted(self.notes.items())])
        self._structure = None

    def path(self, target, *, structural=False):
        adjacency = self.structure().children if structural else self.outgoing
        queue, parents = deque([self.root]), {self.root: None}
        if self.root not in self.notes or target not in self.notes:
            return []
        while queue:
            current = queue.popleft()
            if current == target:
                result = []
                while current is not None:
                    result.append(current)
                    current = parents[current]
                return list(reversed(result))
            for child in sorted(adjacency.get(current, ())):
                if child not in parents:
                    parents[child] = current
                    queue.append(child)
        return []

    def structure(self):
        if self._structure is None:
            self._structure = Structure(self)
        return self._structure


class Structure:
    def __init__(self, graph):
        self.graph, self.children = graph, defaultdict(set)
        for parent, targets in graph.outgoing.items():
            for target in targets:
                roles = set(graph.notes[target]["tags"])
                if parent == graph.root and "main" in roles or parent != graph.root \
                        and set(graph.notes[parent]["tags"]) & {"main", "key"} and "key" in roles:
                    self.children[parent].add(target)
        counts, queue, seen = {graph.root: 1}, deque([graph.root]), set()
        while queue:
            parent = queue.popleft()
            for child in sorted(self.children[parent]):
                edge = (parent, child, counts[parent])
                if edge in seen:
                    continue
                seen.add(edge)
                old = counts.get(child, 0)
                counts[child] = min(2, old+counts[parent])
                if old != counts[child]:
                    queue.append(child)
        self.eligible = {p for p, n in counts.items() if p in graph.notes and p != graph.root and n == 1
                         and not {"main", "key"} <= set(graph.notes[p]["tags"])}
        # Unique structural paths are traversed once, without a per-target BFS.
        self.paths = {graph.root: [graph.root]}
        queue = deque([graph.root])
        while queue:
            parent = queue.popleft()
            for child in sorted(self.children[parent]):
                if child in self.eligible and child not in self.paths:
                    self.paths[child] = [*self.paths[parent], child]
                    queue.append(child)
        self.eligible.intersection_update(self.paths)
        self.sha = digest({p: {"sha": graph.notes[p]["sha"], "children": sorted(self.children[p])}
                           for p in sorted(counts) if p in graph.notes})

    def memberships(self, path):
        if path in self.eligible:
            return {path}
        return self.graph.outgoing.get(path, set()) & self.eligible

    def members(self, anchor):
        descendants = {p for p, chain in self.paths.items() if anchor in chain}
        result = set(descendants)
        for child in descendants:
            result.update(p for p in self.graph.incoming[child]
                          if p not in self.eligible and p != self.graph.root)
        return result
