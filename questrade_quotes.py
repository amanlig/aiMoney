"""Fetch Questrade covered-call quote scenarios; no account or order endpoints."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import getpass
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from simulator import number, evaluate_portfolio
from fx_sources import select_latest, timestamp


class ImporterError(ValueError):
    """An explicitly safe message containing no credentials or server payload."""


class BrokerNotConfigured(ImporterError):
    """The app has no usable local broker authorization; no network call was made."""


def saved_refresh_token(path):
    path=Path(path)
    if not path.is_file():
        raise BrokerNotConfigured('Questrade authorization is not configured for this app. Live quote refresh is unavailable.')
    if path.stat().st_mode & 0o077:
        raise BrokerNotConfigured('The Questrade authorization file must be private. Check this app’s broker setup.')
    try:
        value=json.loads(path.read_text()).get('refresh_token')
    except (OSError,ValueError,AttributeError):
        raise BrokerNotConfigured('The saved Questrade authorization is invalid. Reconnect this app to Questrade.') from None
    if not isinstance(value,str) or not value.strip() or any(c.isspace() for c in value):
        raise BrokerNotConfigured('The saved Questrade authorization is invalid. Reconnect this app to Questrade.')
    return value


def fetch(url, token=None, json_body=None):
    headers = {'Accept': 'application/json',
               'User-Agent': 'CoveredCallSimulator/1.0 (Python urllib)'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None
    if json_body is not None:
        if urlparse(url).path != '/v1/markets/quotes/options':
            raise ImporterError('POST is restricted to read-only option market data')
        headers['Content-Type'] = 'application/json'
        data = json.dumps(json_body).encode()
    request = Request(url, headers=headers, data=data)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if not token and error.code == 403:
            content_type = error.headers.get('Content-Type', '').lower() if error.headers else ''
            kind = 'HTML' if 'html' in content_type else 'JSON' if 'json' in content_type else 'unknown format'
            raise ImporterError(
                f'Authorization endpoint returned HTTP 403 ({kind} response). '
                'This does not identify a market-data permission problem. '
                'Confirm the token is a live-account manual authorization token, '
                'not the app consumer key or secret. If a fresh token still fails, '
                'contact Questrade API support with this status and response format.') from None
        hint = ('Generate a fresh manual authorization token in API Centre.'
                if not token and error.code in (400, 401)
                else 'Check API authorization and market-data permissions.')
        raise ImporterError(f'Questrade returned HTTP {error.code}. {hint}') from None
    except URLError:
        raise ImporterError('Could not connect to Questrade; check network access.') from None


def authorize(path, new_token=False):
    path=Path(path)
    if not new_token and path.is_file():
        refresh=saved_refresh_token(path)
    elif new_token or sys.stdin.isatty():
        refresh=getpass.getpass('Questrade manual authorization token (hidden): ').strip()
    else:
        refresh=saved_refresh_token(path)
    if not refresh:
        raise ImporterError('An API token is required')
    response = fetch('https://login.questrade.com/oauth2/token?' + urlencode(
        {'grant_type': 'refresh_token', 'refresh_token': refresh}))
    # Persist rotated refresh token immediately, even if later quote capture fails.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump({'refresh_token': response['refresh_token']}, file)
    server = response['api_server'].rstrip('/')
    parsed = urlparse(server)
    if (parsed.scheme != 'https' or not parsed.hostname
            or not parsed.hostname.endswith('.iq.questrade.com')
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.path or parsed.query or parsed.fragment):
        raise ImporterError('Unexpected Questrade API server')
    return server + '/v1/', response['access_token']


def call_id(chain, position):
    matches = []
    expiries = chain.get('optionChain', chain.get('options'))
    if not isinstance(expiries, list):
        raise ImporterError('Option-chain response contains neither an optionChain nor options list')
    for expiry in expiries:
        if expiry['expiryDate'][:10] != position['call_expiry']:
            continue
        for root in expiry['chainPerRoot']:
            if root.get('root', root.get('optionRoot')) != position['symbol']:
                continue
            if root.get('multiplier') is not None and Decimal(str(root['multiplier'])) != Decimal(str(position['contract_multiplier'])):
                continue
            for strike in root['chainPerStrikePrice']:
                if Decimal(str(strike['strikePrice'])) == Decimal(str(position['call_strike_native_currency'])):
                    matches.append(strike['callSymbolId'])
    if len(matches) != 1:
        raise ImporterError(f"{position['symbol']}: could not uniquely match standard call strike/expiry/multiplier")
    return matches[0]


def validate_contract(detail, position, stock_id):
    deliverables = detail.get('optionContractDeliverables', {})
    underlyings = deliverables.get('underlyings', [])
    valid = (detail.get('optionType') == 'Call'
             and detail.get('optionRoot') == position['symbol']
             and str(detail.get('optionExpiryDate', ''))[:10] == position['call_expiry']
             and number(detail.get('optionStrikePrice'), 'option strike') == number(position['call_strike_native_currency'], 'saved strike')
             and detail.get('currency') == 'USD'
             and len(underlyings) == 1
             and str(underlyings[0].get('underlyingSymbolId')) == str(stock_id)
             and number(underlyings[0].get('multiplier'), 'deliverable multiplier') == number(position['contract_multiplier'], 'saved multiplier')
             and number(deliverables.get('cashInLieu'), 'cash deliverable') == 0)
    if not valid:
        raise ImporterError('Call contract details do not match the saved standard USD covered call')


def quote_price(quote, side):
    if quote.get('isHalted') is not False:
        raise ImporterError('Quote has halted or unknown trading status')
    price = number(quote.get(side + 'Price'), side + 'Price')
    if price <= 0 or number(quote.get(side + 'Size'), side + 'Size') <= 0:
        raise ImporterError(f'No positive {side} quote/size')
    if 'delay' not in quote:
        raise ImporterError('Missing quote delay status')
    return price


def capture(document, api, usd_cad, usd_sell_cad=None, usd_buy_cad=None):
    overrides, records = {}, []
    if (usd_sell_cad is None) != (usd_buy_cad is None):
        raise ImporterError('Supply both USD sell and buy rates, in CAD per USD')
    if usd_sell_cad is not None:
        usd_sell_cad = number(usd_sell_cad, 'USD sell rate')
        usd_buy_cad = number(usd_buy_cad, 'USD buy rate')
        if usd_sell_cad <= 0 or usd_buy_cad < usd_sell_cad:
            raise ImporterError('Rates require 0 < USD sell rate <= USD buy rate, both in CAD per USD')
    for position in document['positions']:
        if not position.get('call_contracts', 0):
            continue
        symbol = position['symbol']
        if symbol not in {'ASTS', 'INTC', 'MU', 'NVDA', 'RKLB', 'QBTS'}:
            raise ImporterError('Importer currently supports the six saved US covered-call symbols')
        found = api('symbols/search?' + urlencode({'prefix': symbol}))['symbols']
        exact = [row for row in found if row['symbol'] == symbol and row.get('isTradable') is True]
        if len(exact) != 1:
            raise ImporterError(f'{symbol}: could not uniquely resolve underlying')
        stock_id = exact[0]['symbolId']
        option_id = call_id(api(f'symbols/{stock_id}/options'), position)
        details = api(f'symbols/{option_id}')['symbols']
        if len(details) != 1 or str(details[0].get('symbolId')) != str(option_id):
            raise ImporterError('Could not resolve call contract details')
        validate_contract(details[0], position, stock_id)
        quotes = api('markets/quotes?' + urlencode({'ids': f'{stock_id},{option_id}'}))['quotes']
        by_id = {row['symbolId']: row for row in quotes}
        stock, option = by_id[stock_id], by_id[option_id]
        bid, ask = quote_price(stock, 'bid'), quote_price(option, 'ask')
        net_usd = (number(position['shares'], 'shares') * bid
                   - number(position['call_contracts'], 'contracts')
                   * number(position['contract_multiplier'], 'multiplier') * ask)
        direction = 'sell USD for CAD' if net_usd >= 0 else 'buy USD with CAD'
        applied_fx = usd_cad if usd_sell_cad is None else (usd_sell_cad if net_usd >= 0 else usd_buy_cad)
        # Existing book costs are CAD equivalents. Convert quote prices to CAD,
        # preserving those costs rather than treating CAD basis as USD basis.
        if position['currency'] != 'CAD' or Decimal(position['fx_to_cad']) != 1:
            raise ImporterError('Importer requires the saved CAD-equivalent inputs')
        overrides[symbol] = {'stock_bid': str(bid * applied_fx),
                             'call_ask': str(ask * applied_fx), 'fx_to_cad': '1'}
        records.append({'symbol': symbol, 'stock': stock, 'call': option,
                        'net_exit_usd_before_fees': str(net_usd),
                        'fx_conversion_direction': direction,
                        'applied_cad_per_usd': str(applied_fx)})
    return {'name': 'Questrade captured bids/asks', 'overrides': overrides,
            'captured_at_utc': datetime.now(timezone.utc).isoformat(),
            'usd_to_cad_assumption': str(usd_cad),
            'fx_settlement': {'mode': 'Both legs settle in USD; convert net exit proceeds per position',
                              'usd_sell_cad': str(usd_sell_cad) if usd_sell_cad is not None else None,
                              'usd_buy_cad': str(usd_buy_cad) if usd_buy_cad is not None else None,
                              'rate_kind': 'User-supplied directional conversion rates' if usd_sell_cad is not None else 'Reference rate without broker spread',
                              'fees': 'Saved closing_fees are CAD equivalents deducted after net USD conversion. Netting across multiple positions is not modeled.'},
            'quotes': records,
            'note': 'Capture time is not a bid/ask timestamp. lastTradeTime is a trade timestamp. Check delay and sizes; fills are not guaranteed.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('portfolio', type=Path)
    parser.add_argument('--fx-quotes', type=Path, help='JSON array of timestamped Questrade Global bid/ask quotes')
    parser.add_argument('--usd-sell-cad', help='CAD received per USD sold; supply with --usd-buy-cad')
    parser.add_argument('--usd-buy-cad', help='CAD paid per USD bought; supply with --usd-sell-cad')
    parser.add_argument('--fx-observed-at', help='Questrade Global quote date/time with UTC offset, required with directional rates')
    parser.add_argument('--output', type=Path, required=True, help='New local scenario capture file')
    parser.add_argument('--token-file', type=Path, default=Path(__file__).parent / '.secrets/questrade.json')
    parser.add_argument('--new-token', action='store_true', help='Prompt for a fresh manual token instead of using saved authorization')
    args = parser.parse_args()
    stage = 'reading portfolio input'
    try:
        document = json.loads(args.portfolio.read_text())
        evaluate_portfolio(document)
        if args.output.exists():
            raise ImporterError('Choose a new output filename to preserve earlier captures')
        if (args.usd_sell_cad is None) != (args.usd_buy_cad is None):
            raise ImporterError('Supply both --usd-sell-cad and --usd-buy-cad')
        if args.usd_sell_cad is not None:
            sell = number(args.usd_sell_cad, 'USD sell rate')
            buy = number(args.usd_buy_cad, 'USD buy rate')
            if sell <= 0 or buy < sell:
                raise ImporterError('Rates require 0 < USD sell rate <= USD buy rate, both in CAD per USD')
        stage = 'validating Questrade Global FX quote'
        if args.fx_quotes:
            if args.usd_sell_cad is not None:
                raise ImporterError('Use either --fx-quotes or directional rates, not both')
            supplied = json.loads(args.fx_quotes.read_text())
            if not isinstance(supplied, list):
                raise ImporterError('--fx-quotes must contain a JSON array')
            supplied = [q for q in supplied if q.get('source') == 'Questrade Global'
                        and 'bid_cad_per_usd' in q and 'ask_cad_per_usd' in q]
            selected, fx_metadata = select_latest(supplied)
            args.usd_sell_cad = selected['bid_cad_per_usd']
            args.usd_buy_cad = selected['ask_cad_per_usd']
        elif args.usd_sell_cad is not None and args.fx_observed_at:
            timestamp(args.fx_observed_at)
            selected, fx_metadata = select_latest([{
                'source': 'Questrade Global', 'observed_at': args.fx_observed_at,
                'cad_per_usd': str(sell), 'bid_cad_per_usd': str(sell),
                'ask_cad_per_usd': str(buy),
                'kind': 'Owner-supplied FX trading bid/ask; TFSA conversion applicability unverified'}])
        else:
            raise ImporterError('Supply Questrade Global bid/ask and --fx-observed-at, or --fx-quotes. No external FX fallback is used.')
        fx = number(args.usd_sell_cad, 'Questrade Global USD sell bid')
        print(f"USD/CAD: {fx} CAD per USD · {fx_metadata.get('selected_source', fx_metadata.get('source'))} · observation: {fx_metadata.get('selected_observed_at', fx_metadata.get('observation_date')) or 'not supplied'}")
        stage = 'authorizing with Questrade'
        server, token = authorize(args.token_file, args.new_token)
        def api(route):
            nonlocal stage
            stage = 'requesting ' + route.split('?')[0]
            return fetch(server + route, token)
        scenario = capture(document, api, fx, args.usd_sell_cad, args.usd_buy_cad)
        scenario['fx_metadata'] = fx_metadata
        stage = 'validating captured quotes'
        evaluate_portfolio(document, scenario)
        stage = 'saving quote capture'
        args.output.write_text(json.dumps([scenario], indent=2) + '\n')
        print(f'Saved quote scenario: {args.output}')
        delayed = any(q[leg]['delay'] for q in scenario['quotes'] for leg in ('stock', 'call'))
        print('Contains delayed quotes.' if delayed else 'Questrade reports no delay; capture is not a guaranteed fill.')
    except ImporterError as error:
        parser.exit(2, f'Capture failed while {stage}: {error}\n')
    except KeyError as error:
        known_fields = {'options', 'expiryDate', 'chainPerRoot', 'chainPerStrikePrice',
                        'strikePrice', 'callSymbolId', 'symbols', 'symbolId', 'quotes',
                        'refresh_token', 'access_token', 'api_server'}
        field = error.args[0] if error.args and error.args[0] in known_fields else '(unrecognized field)'
        parser.exit(2, f'Capture failed while {stage}: missing field {field}. Credentials were not printed.\n')
    except (ValueError, TypeError, OSError) as error:
        # Avoid printing exception URLs or API payloads that could contain tokens.
        parser.exit(2, f'Capture failed while {stage} ({type(error).__name__}). Credentials and server payloads were not printed.\n')


if __name__ == '__main__':
    main()
