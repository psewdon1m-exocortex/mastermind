"""Exact, bounded block search. SQLite vectors remain the rebuildable source.

The Python implementation is the qualification oracle. Faiss scores the same
scoped rows with IndexFlatIP; this is exhaustive search, not ANN. Cached native
indexes are content addressed and never deserialized from external files.
"""
import hashlib
import math
import struct
import threading
from collections import OrderedDict

from .errors import DomainError

VECTOR = struct.Struct('<384f')


class ExactSearch:
    def __init__(self, backend='faiss', cache_bytes=32*1024**2):
        if backend not in {'faiss', 'python'}:
            raise ValueError('Unsupported exact-search backend')
        self.requested = backend
        self.backend = backend
        self.cache, self.retained = OrderedDict(), 0
        self.budget, self.lock = cache_bytes, threading.Lock()
        self.failure = None
        self.faiss = self.np = None
        if backend == 'faiss':
            try:
                import faiss
                import numpy as np
                self.faiss, self.np = faiss, np
            except ImportError:
                self.backend, self.failure = 'python', 'FAISS_UNAVAILABLE'

    def score(self, rows, queries):
        """Return scores in input-row order, independent of native internal IDs."""
        if not rows:
            return [[] for _ in queries]
        if len(rows) > 2048 or not 1 <= len(queries) <= 8:
            raise DomainError('VECTOR_LIMIT', 'Exact search exceeds its bounded block size.', 422)
        try:
            if any(len(q) != 384 or any(type(v) not in (int, float) or not math.isfinite(v) for v in q) for q in queries):
                raise ValueError
            if self.backend == 'python':
                vectors = [VECTOR.unpack(r['vector']) for r in rows]
                if any(not math.isfinite(v) for vector in vectors for v in vector):
                    raise ValueError
                return [[sum(a*b for a, b in zip(q, v, strict=True)) for v in vectors] for q in queries]
            blob = b''.join(r['vector'] for r in rows)
            if len(blob) != len(rows)*VECTOR.size:
                raise ValueError
            key = hashlib.sha256(blob).digest()
            np, faiss = self.np, self.faiss
            # FAISS/OpenMP thread count is thread-local on supported runtimes.
            faiss.omp_set_num_threads(2)
            with self.lock:
                index = self.cache.get(key)
                if index is None:
                    vectors = np.frombuffer(blob, dtype='<f4').reshape(len(rows), 384)
                    if not np.isfinite(vectors).all():
                        raise ValueError
                    index = faiss.IndexFlatIP(384)
                    index.add(vectors)
                    while self.cache and self.retained+len(blob) > self.budget:
                        _, old = self.cache.popitem(last=False)
                        self.retained -= old.ntotal*VECTOR.size
                    if len(blob) <= self.budget:
                        self.cache[key] = index
                        self.retained += len(blob)
                else:
                    self.cache.move_to_end(key)
            query = np.ascontiguousarray(queries, dtype='float32')
            if query.shape != (len(queries), 384) or not np.isfinite(query).all():
                raise ValueError
            scores, ids = index.search(query, len(rows))
            ordered = np.empty_like(scores)
            np.put_along_axis(ordered, ids, scores, axis=1)
            return ordered.tolist()
        except (ValueError, struct.error, RuntimeError):
            raise DomainError('REINDEX_REQUIRED', 'The derived vector block failed validation; rebuild it.', 503) from None

    def clear(self):
        with self.lock:
            self.cache.clear()
            self.retained = 0

    def status(self):
        return {'backend': self.backend, 'requested_backend': self.requested, 'exact': True,
                'error': self.failure, 'cache_bytes': self.retained, 'cache_limit': self.budget}
