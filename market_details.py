"""Capture stock depth and exact held-call Greeks; no account or order requests."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from urllib.parse import urlencode

from questrade_quotes import authorize, fetch, call_id, validate_contract, ImporterError

ROOT = Path(__file__).resolve().parent
INPUTS = ['book-values-unassigned.json', 'tfsa-closing.json', 'lira-closing.json']


def metrics(quote):
    result = {}
    for field in ('bidPrice', 'askPrice', 'bidSize', 'askSize', 'delta', 'theta', 'volatility', 'delay'):
        value = quote.get(field)
        result[field] = value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None
    result['isHalted'] = quote.get('isHalted')
    return result


def capture(api, options_api, documents):
    holdings = {}
    for document in documents:
        for p in document['positions']:
            if not p.get('call_contracts'):
                continue
            key = (p['symbol'], p['call_expiry'], str(p['call_strike_native_currency']))
            if key not in holdings:
                holdings[key] = {'position': p, 'accounts': []}
            holdings[key]['accounts'].append(document['account_type'])
    stocks, options, errors = {}, [], {}
    for symbol in sorted({k[0] for k in holdings}):
        try:
            matches = [r for r in api('symbols/search?' + urlencode({'prefix': symbol}))['symbols']
                       if r['symbol'] == symbol and r.get('isTradable') is True]
            if len(matches) != 1:
                raise ImporterError('Underlying could not be uniquely resolved')
            stock_id = matches[0]['symbolId']
            quotes = api('markets/quotes?' + urlencode({'ids': stock_id}))['quotes']
            stock = next(q for q in quotes if q['symbolId'] == stock_id)
            stocks[symbol] = metrics(stock)
            chain = api(f'symbols/{stock_id}/options')
            for key, holding in holdings.items():
                if key[0] != symbol:
                    continue
                p = holding['position']
                record = dict(symbol=symbol, expiry=p['call_expiry'],
                              strike=p['call_strike_native_currency'], accounts=holding['accounts'])
                try:
                    option_id = call_id(chain, p)
                    details = api(f'symbols/{option_id}')['symbols']
                    if len(details) != 1 or details[0]['symbolId'] != option_id:
                        raise ImporterError('Ambiguous contract')
                    validate_contract(details[0], p, stock_id)
                    response = options_api([option_id])
                    quotes = response.get('optionQuotes', response.get('quotes', []))
                    quote = next(q for q in quotes if q['symbolId'] == option_id)
                    record.update(metrics(quote))
                except (ImporterError, OSError, KeyError, ValueError, TypeError, StopIteration):
                    record['error'] = 'Exact-contract option data unavailable.'
                options.append(record)
        except (ImporterError, OSError, KeyError, ValueError, TypeError, StopIteration):
            errors[symbol] = 'Stock or option-chain data unavailable.'
    return dict(captured_at=datetime.now(timezone.utc).isoformat(), source='Questrade API',
                stocks=stocks, options=options, errors=errors)


def main():
    try:
        documents = [json.loads((ROOT/'data'/name).read_text()) for name in INPUTS]
        base, token = authorize(ROOT/'.secrets/questrade.json')
        document = capture(lambda route: fetch(base+route, token),
                           lambda ids: fetch(base+'markets/quotes/options', token,
                                             json_body={'optionIds': ids}), documents)
        if not document['stocks']:
            raise ImporterError('No stock details captured; previous capture retained')
        path = ROOT/'reports/market-details.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(document, indent=2))
        temporary.replace(path)
        available = sum('error' not in option for option in document['options'])
        print(f'Saved {len(document["stocks"])} stocks and {available} held-call quotes with broker Greek fields.')
    except ImporterError as error:
        raise SystemExit(f'Market details capture stopped: {error}') from None
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('Market details capture stopped; credentials and server payloads were not printed.') from None


if __name__ == '__main__':
    main()
