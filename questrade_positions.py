"""Sync the unique active Questrade LIRA into the private USD account snapshot.

GET account/position/symbol/quote endpoints only; no balances, activities or orders.
Account numbers and credentials are neither logged nor saved in the report/page.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlencode

from questrade_quotes import authorize, fetch, ImporterError, quote_price, validate_contract
from simulator import count, number

ROOT = Path(__file__).resolve().parent


def select_lira(accounts):
    candidates = [a for a in accounts if a.get('type') == 'LIRA' and a.get('status') == 'Active']
    if len(candidates) != 1:
        raise ImporterError('Expected exactly one active LIRA; no account positions were requested')
    account = candidates[0]
    if not str(account.get('number', '')).isdigit():
        raise ImporterError('Invalid LIRA account identifier')
    return account


def signed_cost(row):
    value = row.get('totalCost')
    return None if value is None or isinstance(value, bool) else number(value, 'position cost', nonnegative=False)


def normalize(source, details, quotes):
    rows = [r for r in source['positions'] if number(r['openQuantity'], 'quantity', nonnegative=False) != 0]
    if len({r['symbolId'] for r in rows}) != len(rows):
        raise ImporterError('Duplicate position symbols are unsupported')
    by_id = {str(r['symbolId']): r for r in rows}
    stock_rows, option_rows = [], []
    for row in rows:
        detail = details[str(row['symbolId'])]
        if row.get('isUnderReorg') is True:
            raise ImporterError('A LIRA holding is under reorganization; saved snapshot was not replaced')
        if detail.get('currency') != 'USD':
            raise ImporterError('LIRA sync currently requires USD holdings; mixed currencies are unsupported')
        if detail.get('securityType') == 'Stock':
            if number(row['openQuantity'], 'quantity', nonnegative=False) <= 0:
                raise ImporterError('Short stocks are unsupported')
            stock_rows.append(row)
        elif detail.get('securityType') == 'Option':
            if detail.get('optionType') != 'Call' or number(row['openQuantity'], 'quantity', nonnegative=False) >= 0:
                raise ImporterError('Only short calls and long stocks are supported')
            option_rows.append(row)
        else:
            raise ImporterError('A LIRA holding has an unsupported security type')
    paired = {}
    for option in option_rows:
        detail = details[str(option['symbolId'])]
        deliverables = detail.get('optionContractDeliverables', {})
        underlyings = deliverables.get('underlyings', [])
        if len(underlyings) != 1:
            raise ImporterError('Adjusted or multiple-underlying calls are unsupported')
        stock_id = str(underlyings[0]['underlyingSymbolId'])
        if stock_id not in by_id or by_id[stock_id] not in stock_rows:
            raise ImporterError('A short call has no matching long stock position')
        if stock_id in paired:
            raise ImporterError('Multiple call series for one stock need separate strategy allocation')
        paired[stock_id] = option
    positions = []
    for stock in stock_rows:
        stock_id = str(stock['symbolId'])
        cost = signed_cost(stock)
        if cost is not None and cost < 0:
            raise ImporterError('Long-stock cost has an unexpected sign')
        position = {'symbol': stock['symbol'], 'currency': 'USD',
                    'shares': count(stock['openQuantity'], 'shares'), 'call_contracts': 0,
                    'contract_multiplier': 100, 'stock_bid': str(quote_price(quotes[stock_id], 'bid')),
                    'call_ask': '0', 'stock_cost_total': str(cost) if cost is not None else None,
                    'call_premium_net_total': '0', 'closing_fees': '0',
                    'source_stock_symbol_id': stock['symbolId'],
                    'broker_stock_market_value': str(stock['currentMarketValue']),
                    'broker_stock_open_pnl': str(stock.get('openPnl')) if stock.get('openPnl') is not None else None}
        if stock_id in paired:
            option = paired[stock_id]
            detail = details[str(option['symbolId'])]
            contracts = count(-number(option['openQuantity'], 'contracts', nonnegative=False), 'contracts')
            if contracts * 100 > position['shares']:
                raise ImporterError('Short calls exceed their stock coverage')
            position.update(call_contracts=contracts, call_expiry=detail['optionExpiryDate'][:10],
                            call_strike_native_currency=str(detail['optionStrikePrice']))
            validate_contract(detail, position, stock['symbolId'])
            premium = signed_cost(option)
            if premium is not None and premium > 0:
                raise ImporterError('Short-call cost has an unexpected sign')
            position.update(call_ask=str(quote_price(quotes[str(option['symbolId'])], 'ask')),
                            call_premium_net_total=str(-premium) if premium is not None else None,
                            source_call_symbol_id=option['symbolId'],
                            broker_call_market_value=str(option['currentMarketValue']),
                            broker_call_open_pnl=str(option.get('openPnl')) if option.get('openPnl') is not None else None)
        positions.append(position)
    if not any(p['call_contracts'] for p in positions):
        raise ImporterError('No covered-call positions in LIRA; saved snapshot was not replaced')
    return {'account_label': 'LIRA', 'account_type': 'LIRA',
            'captured_at_utc': source['captured_at_utc'], 'position_source': 'Questrade API',
            'quote_context': 'Questrade API holdings with captured stock bids and short-call asks in USD. Capture time is not a bid/ask timestamp; check delay/size flags. No guaranteed fill.',
            'cost_basis_context': 'Questrade totalCost for current stock/call positions; short-call cost magnitude is a premium proxy, not verified lifetime cash flows. Earlier rolls, dividends and realized P/L are excluded.',
            'cash_status': 'Not retrieved; account cash excluded', 'positions': positions,
            'source_quotes': list(quotes.values())}


def capture_lira(api):
    account = select_lira(api('accounts')['accounts'])
    rows = api(f'accounts/{account["number"]}/positions')['positions']
    rows = [r for r in rows if number(r['openQuantity'], 'quantity', nonnegative=False) != 0]
    if not rows:
        raise ImporterError('LIRA has no open positions')
    ids = ','.join(str(count(r['symbolId'], 'symbol ID')) for r in rows)
    details_list = api('symbols?' + urlencode({'ids': ids}))['symbols']
    quote_list = api('markets/quotes?' + urlencode({'ids': ids}))['quotes']
    details = {str(r['symbolId']): r for r in details_list}
    quotes = {str(r['symbolId']): r for r in quote_list}
    if any(str(r['symbolId']) not in details or str(r['symbolId']) not in quotes for r in rows):
        raise ImporterError('Missing symbol details or market quotes')
    source = {'account_type': 'LIRA', 'captured_at_utc': datetime.now(timezone.utc).isoformat(),
              'positions': rows}
    document = normalize(source, details, quotes)
    report = dict(source, symbol_details=list(details.values()), quotes=quote_list)
    return document, report


def write_private(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        json.dump(document, file, indent=2)
        file.write('\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token-file', type=Path, default=ROOT/'.secrets/questrade.json')
    parser.add_argument('--new-token', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT/'data/lira-closing.json')
    parser.add_argument('--archive-chart', action='store_true', help='Explicitly regenerate the archived dashboard')
    parser.add_argument('--no-chart', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        base, token = authorize(args.token_file, args.new_token)
        def api(route):
            return fetch(base + route, token)
        document, report = capture_lira(api)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        if args.output.exists():
            write_private(args.output.with_name(f'{args.output.stem}-before-{stamp}.json'), json.loads(args.output.read_text()))
        report_path = ROOT/'reports'/f'lira-positions-{stamp}.json'
        write_private(report_path, report)
        write_private(args.output, document)
        covered = [p for p in document['positions'] if p['call_contracts']]
        print(f'Synced LIRA: {len(covered)} covered stock positions; {len(document["positions"])-len(covered)} stock-only positions preserved.')
        print(f'Saved USD snapshot: {args.output}')
        print(f'Saved source positions and quotes: {report_path}')
        if args.archive_chart and not args.no_chart:
            subprocess.run([sys.executable, str(ROOT/'archive/equity-dashboard/chart.py'), '--lira', str(args.output)], check=True)
    except ImporterError as error:
        parser.exit(2, f'LIRA sync stopped: {error}. Credentials and account numbers were not printed.\n')
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f'LIRA sync stopped ({type(error).__name__}). Credentials, account numbers and server payloads were not printed.\n')


if __name__ == '__main__':
    main()
