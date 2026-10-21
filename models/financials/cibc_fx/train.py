"""Train and evaluate using local reviewed samples; never modifies SQLite."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from model import DIRECTIONS, fit, metrics, positive, split_dates

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(path):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute('SELECT * FROM samples ORDER BY settlement_date,id')]
    valid, excluded = [], []
    for row in rows:
        reason = None
        try:
            date.fromisoformat(row['settlement_date'])
        except (ValueError, TypeError):
            reason = 'invalid settlement date'
        if row['direction'] not in DIRECTIONS:
            reason = 'unknown direction'
        elif not all(positive(row[k]) for k in ('yahoo_close','applied_rate','usd_amount','cad_amount')):
            reason = 'missing or invalid rate/amount'
        elif abs(row['usd_amount']*row['applied_rate']-row['cad_amount']) > max(.10,row['usd_amount']*.000051):
            reason = 'amounts do not reconcile'
        if reason:
            excluded.append({'id': row['id'], 'reason': reason})
        else:
            valid.append(row)
    return valid, excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT/'data/fx-samples.sqlite3')
    args = parser.parse_args()
    rows, excluded = load(args.database)
    earlier, later = split_dates(rows)
    candidate = fit(earlier)
    for direction in DIRECTIONS:
        if not any(r['direction'] == direction for r in later):
            raise ValueError(f'Holdout needs samples for {direction}.')
    report = {'evaluation': 'Chronological holdout; same settlement dates never cross split.',
              'limitation': 'Retrospective reference-rate estimation, not a validated live forecast. Holdout transactions share dates and are not independent.',
              'train_samples': len(earlier), 'test_samples': len(later),
              'train_end': max(r['settlement_date'] for r in earlier),
              'test_start': min(r['settlement_date'] for r in later),
              'excluded': excluded, 'overall': metrics(candidate,later),
              'by_direction': {d: metrics(candidate,[r for r in later if r['direction']==d]) for d in DIRECTIONS},
              'by_usd_size': {name: metrics(candidate,[r for r in later if low <= r['usd_amount'] < high])
                              for name,low,high in [('under_1000',0,1000),('1000_to_10000',1000,10000),('10000_plus',10000,float('inf'))]},
              'evaluated_parameters': candidate['parameters']}
    fitted = fit(rows)
    fitted.update(trained_at=datetime.now(timezone.utc).isoformat(), samples=len(rows),
                  settlement_start=min(r['settlement_date'] for r in rows),
                  settlement_end=max(r['settlement_date'] for r in rows),
                  data_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
                  limitation=report['limitation'])
    for directory, filename, value in [('artifacts','model.json',fitted),('evaluation','holdout.json',report)]:
        target=HERE/directory/filename
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
        temporary.replace(target)
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
