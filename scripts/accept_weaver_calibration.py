"""Accept frozen Weaver placement thresholds only after the recorded test gates pass."""
import argparse
import hashlib
import json
from pathlib import Path

from qualify_context_indexing import evaluate

from mastermind.weaver.graph import digest as record_digest


def accept(directory, target):
    paths = {key: directory/name for key, name in {
        'thresholds': 'placement-thresholds.json', 'calibration': 'placement-calibration.json',
        'test': 'placement-test.json'}.items()}
    values = {key: json.loads(path.read_text(encoding='utf-8')) for key, path in paths.items()}
    frozen, calibration, test = (values[key] for key in ('thresholds', 'calibration', 'test'))
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert frozen['calibration_report_sha256'] == record_digest({k: v for k, v in calibration.items() if k != 'status'})
    assert test['calibration_sha256'] == digest(paths['thresholds'])
    assert calibration['phase'] == 'calibration' and test['phase'] == 'test' and test['status'] == 'PASS'
    for key in ('corpus_sha256', 'embedding_sha256', 'search_representation'):
        assert len({value[key] for value in values.values()}) == 1
    assert frozen['search_representation'] == 'search-content.v2'
    for variant, operating_point in (('complete', 'complete'), ('vector', 'vector'), ('curator', 'complete:curator')):
        rows = test['variants'][variant]['cases']
        assert not {r['id'] for r in rows} & {r['id'] for r in calibration['variants']['complete']['cases']}
        measured = evaluate(rows, frozen['variants'][operating_point])
        assert measured == test['variants'][variant]['metrics']
        assert measured['auto_decisions'] >= 50 and measured['precision'] >= .98 and measured['must_pool_auto'] == 0
    frozen.update(qualified=True, version='weaver.calibration.20261002.v2',
        rejection_guard_version='explicit-topic-exclusions.v1',
        evidence={key: digest(path) for key, path in paths.items()},
        measured={key: value['metrics'] for key, value in test['variants'].items()},
        limitations=['Authored grouped synthetic bilingual corpus, not a universal accuracy estimate.',
                    'Thresholds were frozen on 100 calibration cases before 100 separate test cases.',
                    'Bibliotekar refined two test cases; the small sample does not justify enabling it by default.',
                    'No fresh paid-provider legacy comparison; earlier context-indexing results are historical.'])
    target.write_text(json.dumps(frozen, indent=2)+'\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, default=Path('artifacts/weaver'))
    parser.add_argument('--target', type=Path, default=Path('src/mastermind/weaver/calibration.json'))
    args = parser.parse_args()
    accept(args.reports, args.target)
    print('PASS: Weaver placement calibration and frozen test provenance accepted.')


if __name__ == '__main__':
    main()
