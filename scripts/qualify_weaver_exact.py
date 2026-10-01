"""Bounded synthetic-vector CPU benchmark; this measures speed/parity, not semantics."""
import argparse
import json
import math
import statistics
import time
from pathlib import Path

import numpy as np
import psutil

from mastermind.vector_engine import ExactSearch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--vectors', type=int, default=12000)
    args = parser.parse_args()
    if not 100 <= args.vectors <= 50000:
        raise ValueError('Use 100–50000 vectors for bounded qualification')
    rng = np.random.default_rng(811)
    vectors = rng.normal(size=(args.vectors, 384)).astype('float32')
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    rows = [{'vector': vector.tobytes()} for vector in vectors]
    queries = rng.normal(size=(20, 384)).astype('float32')
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)
    queries = queries.tolist()
    report = {'schema': 'weaver.exact-benchmark.v1', 'vectors': args.vectors, 'queries': len(queries),
              'dimensions': 384, 'native_threads': 2, 'origin': 'seeded normalized float32 performance fixture',
              'semantic_quality_claim': False, 'results': {}}
    answers = {}
    for backend in ('python', 'faiss'):
        engine = ExactSearch(backend)
        timings, outputs = [], []
        for query in queries:
            start = time.perf_counter()
            scores = []
            for offset in range(0, len(rows), 2048):
                scores.extend(engine.score(rows[offset:offset+2048], [query])[0])
            outputs.append(scores)
            timings.append((time.perf_counter()-start)*1000)
        answers[backend] = outputs
        report['results'][backend] = {'p50_ms': statistics.median(timings),
            'p95_ms': sorted(timings)[math.ceil(len(timings)*.95)-1], 'cold_ms': timings[0],
            'cache_bytes': engine.retained, 'rss_bytes': psutil.Process().memory_info().rss}
        engine.clear()
    delta = np.max(np.abs(np.array(answers['python'])-np.array(answers['faiss'])))
    assert delta < 2e-6
    for reference, actual in zip(answers['python'], answers['faiss'], strict=True):
        assert np.argsort(reference)[-10:].tolist() == np.argsort(actual)[-10:].tolist()
    report['max_absolute_error'] = float(delta)
    report['speedup_p50'] = report['results']['python']['p50_ms']/report['results']['faiss']['p50_ms']
    report['status'] = 'PASS'
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
