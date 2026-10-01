import random
import struct

import pytest

from mastermind.errors import DomainError
from mastermind.vector_engine import ExactSearch


def test_faiss_exhaustive_results_match_reference_including_ties_and_input_order():
    rng = random.Random(812)
    rows = [{'vector': struct.pack('<384f', *[rng.uniform(-1, 1) for _ in range(384)])} for _ in range(137)]
    rows += [rows[3], rows[3]]
    queries = [[rng.uniform(-1, 1) for _ in range(384)] for _ in range(4)]
    reference = ExactSearch('python').score(rows, queries)
    native = ExactSearch('faiss', cache_bytes=384*4*140)
    assert native.backend == 'faiss', 'The locked Faiss runtime is required for native parity qualification'
    actual = native.score(rows, queries)
    for a, b in zip(actual, reference, strict=True):
        assert a == pytest.approx(b, abs=2e-5)
        assert a[3] == a[-1] == a[-2]
    assert native.score(rows, queries) == actual
    native.score(rows[:50], queries)
    assert native.retained <= native.budget
    native.clear()
    assert native.retained == 0


@pytest.mark.parametrize('backend', ['python', 'faiss'])
def test_exact_engines_reject_corruption_and_invalid_query(backend):
    engine = ExactSearch(backend)
    with pytest.raises(DomainError):
        engine.score([{'vector': b'bad'}], [[0.0]*384])
    with pytest.raises(DomainError):
        engine.score([{'vector': struct.pack('<384f', *([float('nan')]*384))}], [[0.0]*384])
    with pytest.raises(DomainError):
        engine.score([{'vector': bytes(384*4)}], [[float('nan')]*384])
