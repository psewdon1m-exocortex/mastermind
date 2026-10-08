"""Regression gates for the fixed task corpus; not a universal accuracy claim."""
import argparse
import json
from pathlib import Path


def assess(before, after):
    failures = []
    if before['model'] != after['model'] or before['configuration'] != after['configuration']:
        failures.append('Representation/model mismatch: re-baseline explicitly.')
    rows = []
    for task in ('lookup', 'similar'):
        for split in ('calibration', 'test'):
            old, new = before['metrics'][task+'_'+split], after['metrics'][task+'_'+split]
            name = task+'_'+split
            if old['cases'] != new['cases']:
                failures.append(name+': different case counts')
            if new['hit_at_3'] < old['hit_at_3'] or new['recall_at_5'] < old['recall_at_5']:
                failures.append(name+': recall regression')
            # Lookup intentionally trades a small, measured amount of precision
            # for recall. Similar must not add noise to a short recommendation list.
            allowance = 3 if task == 'lookup' else 0
            if new['false_matches_at_3'] > old['false_matches_at_3']+allowance or new['precision_at_3'] < .75:
                failures.append(name+': false-match budget exceeded')
            if new['p50_ms'] > old['p50_ms']*1.5+200 or new['p95_ms'] > old['p95_ms']*2+1000:
                failures.append(name+': latency regression')
            rows.append({'task': name, 'before': old, 'after': new})
    return {'status': 'FAIL' if failures else 'PASS', 'failures': failures, 'comparisons': rows,
            'limits': 'Small fixed synthetic corpus. Independent workorders.json records uncovered weaknesses; '
                      'a PASS does not replace its judgments or deployment acceptance.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = assess(json.loads(args.before.read_text('utf-8')), json.loads(args.after.read_text('utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'failures': result['failures']}))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
