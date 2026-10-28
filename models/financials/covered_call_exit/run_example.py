"""Run the standalone model on synthetic data or your own supplied JSON."""
import argparse
import csv
import json
from pathlib import Path
from model import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(__file__).parent/'examples/sample_input.json')
    parser.add_argument('--output', type=Path, default=Path('example_result.json'))
    parser.add_argument('--csv', type=Path, default=Path('example_rollovers.csv'))
    parser.add_argument('--rate', type=float, default=.04, help='Continuously compounded annual rate, e.g. .04')
    args = parser.parse_args()
    result = evaluate(json.loads(args.input.read_text()), rate=args.rate)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    rows = sorted((r for r in result['rows'] if r['strategy']=='Roll then close'),
                  key=lambda r: (r['total_pl_usd'] is not None, r['total_pl_usd'] or 0), reverse=True)
    fields = ['rank','expiry','strike','estimated_total_position_profit_usd',
              'net_rollover_credit_usd','net_rollover_debit_usd',
              'probability_beating_close','sale_floor_pass_rate','expire_option_cash_only_usd']
    with args.csv.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for i, row in enumerate(rows, 1):
            funding=row['roll_funding']
            writer.writerow(dict(rank=i if row['total_pl_usd'] is not None else None,
                expiry=row['expiry'], strike=row['strike'],
                estimated_total_position_profit_usd=row['total_pl_usd'],
                net_rollover_credit_usd=funding['net_credit_usd'],
                net_rollover_debit_usd=funding['net_debit_usd'],
                probability_beating_close=row['probability_beating_close'],
                sale_floor_pass_rate=row['sale_floor_pass_rate'],
                expire_option_cash_only_usd=row['expire_worthless']['total_pl_usd']))
    close=next(r for r in result['rows'] if r['strategy']=='Close now')
    print(f"Synthetic example: close-now total P/L USD {close['total_pl_usd']:.2f}")
    print(f"Matching rollovers: {len(rows)}; excluded: {result['excluded']}")
    for row in rows:
        value=row['total_pl_usd']
        print(f"{row['expiry']} strike {row['strike']}: total P/L {value}")
    print(f'Wrote {args.output} and {args.csv}')


if __name__ == '__main__':
    main()
