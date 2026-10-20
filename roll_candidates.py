"""Capture listed replacement calls for any saved covered-call holding."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from market_details import metrics
from questrade_quotes import authorize, fetch, call_id, validate_contract, ImporterError

ROOT = Path(__file__).resolve().parent
INPUTS = {'RRSP': 'book-values-unassigned.json', 'TFSA': 'tfsa-closing.json', 'LIRA': 'lira-closing.json'}
SYMBOLS = {'ASTS', 'INTC', 'MU', 'NVDA', 'RKLB', 'QBTS'}


def output_path(account, symbol):
    if account not in INPUTS or symbol not in SYMBOLS:
        raise ImporterError('Unsupported account or stock')
    return ROOT/'reports'/f'roll-candidates-{symbol.lower()}-{account.lower()}.json'


def listed_calls(chain, position, first_expiry, last_expiry, minimum_strike, maximum_strike):
    calls = {}
    for expiry in chain.get('optionChain', chain.get('options', [])):
        day = expiry['expiryDate'][:10]
        if not first_expiry <= day <= last_expiry:
            continue
        for root in expiry['chainPerRoot']:
            if root.get('root', root.get('optionRoot')) != position['symbol']:
                continue
            if root.get('multiplier') is not None and root['multiplier'] != 100:
                continue
            for strike in root['chainPerStrikePrice']:
                value = float(strike['strikePrice'])
                if minimum_strike <= value <= maximum_strike:
                    calls[strike['callSymbolId']] = dict(strike=value, expiry=day,
                                                       symbol_id=strike['callSymbolId'])
    return calls


def capture(api, options_api, position, today, account='LIRA', purchase_price=None):
    found = api('symbols/search?' + urlencode({'prefix': position['symbol']}))['symbols']
    exact = [r for r in found if r['symbol'] == position['symbol'] and r.get('isTradable') is True]
    if len(exact) != 1:
        raise ImporterError('Could not uniquely resolve underlying')
    stock_id = exact[0]['symbolId']
    chain = api(f'symbols/{stock_id}/options')
    old_id = call_id(chain, position)
    old_detail = api(f'symbols/{old_id}')['symbols']
    if len(old_detail) != 1 or old_detail[0]['symbolId'] != old_id:
        raise ImporterError('Could not resolve existing call')
    validate_contract(old_detail[0], position, stock_id)
    stock = next(q for q in api('markets/quotes?' + urlencode({'ids': stock_id}))['quotes'] if q['symbolId'] == stock_id)
    response = options_api([old_id])
    old = next(q for q in response.get('optionQuotes', response.get('quotes', [])) if q['symbolId'] == old_id)
    original_price = purchase_price if purchase_price is not None else float(position['stock_cost_total'])/position['shares']
    if not math.isfinite(original_price) or original_price <= 0:
        raise ImporterError('A positive USD purchase price is required')
    minimum_strike = math.floor(original_price + 5)
    maximum_strike = max(float(position['call_strike_native_currency'])+5, minimum_strike+10)
    first = (today+timedelta(days=30)).isoformat()
    expiries = chain.get('optionChain', chain.get('options', []))
    last = max([first] + [entry['expiryDate'][:10] for entry in expiries])
    all_listed = listed_calls(chain, position, first, last, minimum_strike, float('inf'))
    # Include the next actually listed strike even when it lies above the band.
    nearest = {}
    for option_id, record in all_listed.items():
        if record['strike'] >= original_price + 5 and (record['expiry'] not in nearest or record['strike'] < nearest[record['expiry']][1]['strike']):
            nearest[record['expiry']] = (option_id, record)
    listed = {option_id: record for option_id, record in all_listed.items() if record['strike'] <= maximum_strike}
    listed.update(dict(nearest.values()))
    candidates, errors = [], []
    ids = sorted(listed)
    for start in range(0, len(ids), 50):
        batch = ids[start:start+50]
        details = {d['symbolId']: d for d in api('symbols?' + urlencode({'ids': ','.join(map(str, batch))}))['symbols']}
        valid = []
        for option_id in batch:
            record = listed[option_id]
            p = dict(position, call_expiry=record['expiry'], call_strike_native_currency=str(record['strike']))
            try:
                validate_contract(details[option_id], p, stock_id)
                valid.append(option_id)
            except (ImporterError, KeyError, ValueError, TypeError):
                errors.append('Nonstandard or unverified contract excluded')
        if not valid:
            continue
        response = options_api(valid)
        by_id = {q['symbolId']: q for q in response.get('optionQuotes', response.get('quotes', []))}
        for option_id in valid:
            if option_id not in by_id:
                errors.append('Quote omitted by provider')
                candidates.append(dict(listed[option_id], **metrics({}), validated=True))
                continue
            candidates.append(dict(listed[option_id], **metrics(by_id[option_id]), validated=True))
    captured = datetime.now(timezone.utc).isoformat()
    return dict(symbol=position['symbol'], account=account, captured_at=captured,
                stock=metrics(stock), old_call=dict(metrics(old), strike=float(position['call_strike_native_currency']),
                                                   expiry=position['call_expiry'], captured_at=captured),
                source='Questrade API', candidates=candidates,
                scan=dict(first_expiry=first,last_expiry=last,minimum_strike=minimum_strike,
                          maximum_strike=max([maximum_strike]+[r['strike'] for r in listed.values()]),listed_count=len(listed),errors=errors),
                default_rule='Next listed strike >= purchase + USD 5 for each expiry; later expiry; positive net credit and full displayed size')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', choices=INPUTS, default='LIRA')
    parser.add_argument('--symbol', choices=sorted(SYMBOLS), default='QBTS')
    parser.add_argument('--purchase-price-usd', type=float)
    parser.add_argument('--all', action='store_true', help='Capture every saved covered-call holding')
    args = parser.parse_args()
    try:
        if args.purchase_price_usd is not None and (not math.isfinite(args.purchase_price_usd) or args.purchase_price_usd<=0):
            raise ImporterError('A positive USD purchase price is required')
        base, token = authorize(ROOT/'.secrets/questrade.json')
        for account in INPUTS if args.all else [args.account]:
            document = json.loads((ROOT/'data'/INPUTS[account]).read_text())
            positions = [p for p in document['positions'] if p.get('call_contracts') and (args.all or p['symbol']==args.symbol)]
            if not positions:
                raise ImporterError('No matching saved covered-call holding')
            for position in positions:
                entry_fx = 1 if account=='LIRA' else float(position.get('purchase_fx_to_cad') or 0)
                explicit_purchase = not args.all and args.purchase_price_usd is not None
                if not explicit_purchase and (not math.isfinite(entry_fx) or entry_fx<=0):
                    if args.all:
                        print(f'{account} {position["symbol"]}: skipped; historical purchase FX is missing.', flush=True)
                        continue
                    raise ImporterError('Enter historical purchase FX or supply --purchase-price-usd')
                purchase = args.purchase_price_usd if explicit_purchase else float(position['stock_cost_total'])/position['shares']/entry_fx
                capture_data = capture(lambda route: fetch(base+route, token),
                                       lambda ids: fetch(base+'markets/quotes/options', token, json_body={'optionIds': ids}),
                                       position, datetime.now(ZoneInfo('America/Vancouver')).date(), account, purchase)
                path = output_path(account, position['symbol'])
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(capture_data, indent=2))
                temporary.replace(path)
                print(f'{account} {position["symbol"]}: captured {len(capture_data["candidates"])} verified standard replacement calls.', flush=True)
    except ImporterError as error:
        raise SystemExit(f'Candidate capture stopped: {error}') from None
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        raise SystemExit('Candidate capture stopped; credentials and server payloads were not printed.') from None


if __name__ == '__main__':
    main()
