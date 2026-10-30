"""App adapter for the independent covered-call exit model; read-only market APIs."""
import argparse
from datetime import datetime, timezone, timedelta
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo
from macro_data import fetch as public_fetch
from questrade_quotes import authorize, fetch, call_id, validate_contract, ImporterError, saved_refresh_token, BrokerNotConfigured
from market_details import metrics
import stock_basis
import interest_rates
import option_premiums
import option_rollovers
import position_history
import closed_holdings
import covered_positions
from roll_candidates import INPUTS, listed_calls

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('covered_call_exit_model',ROOT/'models/financials/covered_call_exit/model.py')
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)

class StockHistoryUnavailable(ImporterError):
    """The public stock-history provider failed before broker authorization."""


def source_holdings():
    result=[]
    for account,name in INPUTS.items():
        for p in json.loads((ROOT/'data'/name).read_text())['positions']:
            if p.get('call_contracts'):
                result.append(dict(account=account,**p))
    return result


def inventory():
    result={}
    with covered_positions.transaction() as db:
        excluded={r['source_key'] for r in db.execute('SELECT source_key FROM deleted_position_sources')}
    for account,name in INPUTS.items():
        for p in json.loads((ROOT/'data'/name).read_text())['positions']:
            if p.get('shares'):
                if p.get('call_contracts') and closed_holdings.position_key(dict(account=account,**p)) in excluded:continue
                pair=(account,p['symbol']);result[pair]=result.get(pair,0)+float(p['shares'])
    for basis in stock_basis.records():
        pair=(basis['account'],basis['symbol'])
        if basis['currency']=='USD' or pair not in result:result[pair]=basis['quantity']
    with covered_positions.transaction() as db:
        allocated={}
        for row in covered_positions.rows(db):
            if not covered_positions.is_expired(db,row['id']):
                pair=(row['account'],row['symbol']);allocated[pair]=allocated.get(pair,0)+row['shares']
        for pair,quantity in allocated.items():result[pair]=max(result.get(pair,0),quantity)
    return result


def holdings(*, include_closed=False):
    raw=source_holdings()
    covered_positions.synchronize(raw)
    with covered_positions.transaction() as db:
        covered_positions.retain_stock_holdings(raw,db=db)
        result=[dict(covered_positions.holding(row),option_expired=covered_positions.is_expired(db,row['id'])) for row in covered_positions.rows(db)]
    closed=set() if include_closed else {r['position_key'] for r in closed_holdings.records()}
    return [h for h in result if h['position_id'] not in closed and (include_closed or not h.get('option_expired'))]


def select_holding(request):
    matches=[h for h in holdings() if h['account']==request.get('account') and h['symbol']==request.get('symbol')
             and (not request.get('position_id') or h.get('position_id')==request['position_id'])]
    if len(matches)!=1: raise ValueError('Choose one specific covered-call position.')
    return matches[0]


def capture_path(account,symbol,position_id=None,root=None):
    suffix='-'+position_id if position_id else ''
    return Path(root or ROOT)/'reports'/f'exit-optimizer-{account.lower()}-{symbol.lower()}{suffix}.json'


def load_capture(request,root=None):
    position_id=request.get('position_id')
    path=capture_path(request['account'],request['symbol'],position_id,root)
    if position_id:
        h=select_holding(request)
        if not path.exists():
            if not h.get('legacy_position'): return None
            path=capture_path(request['account'],request['symbol'],root=root)
        if not path.exists(): return None
        capture=json.loads(path.read_text());data=capture.get('inputs',{})
        if data.get('position_id') not in [None,position_id] or data.get('shares')!=h['shares'] or data.get('contracts')!=h['call_contracts'] or (data.get('held',{}).get('expiry'),data.get('held',{}).get('strike'))!=(h['call_expiry'],float(h['call_strike_native_currency'])):
            return None
        data['position_id']=position_id
    else:
        if not path.exists(): return None
        capture=json.loads(path.read_text())
        if not {'held','shares','contracts'} <= capture.get('inputs',{}).keys(): return reaccount_capture(capture)
        matches=[h for h in holdings() if h['account']==request['account'] and h['symbol']==request['symbol']]
        if len(matches)>1: raise ValueError('Select a position ID; this ticker has multiple positions.')
        capture=json.loads(path.read_text())
        if matches and matches[0].get('position_id') and 'held' in capture.get('inputs',{}): capture['inputs']['position_id']=matches[0]['position_id']
    return reaccount_capture(capture)

def closing_quote_snapshot(holding, captured_at):
    """Read the exact saved market capture shown in Close, without broker calls."""
    if not captured_at:
        return None
    path=capture_path(holding['account'],holding['symbol'],holding.get('position_id'))
    if not path.exists() and holding.get('legacy_position'):
        path=capture_path(holding['account'],holding['symbol'])
    try:
        capture=json.loads(path.read_text())
        data=capture['inputs']; held=data['held']
        matches=(not capture.get('scenario') and data.get('captured_at')==captured_at
            and data.get('account')==holding['account'] and data.get('symbol')==holding['symbol']
            and data.get('position_id') in (None,holding.get('position_id'))
            and data.get('shares')==holding['shares'] and data.get('contracts')==holding['call_contracts']
            and held.get('expiry')==holding['call_expiry']
            and held.get('strike')==float(holding['call_strike_native_currency']))
        if not matches:
            raise ValueError()
        fields=('bidPrice','askPrice','bidSize','askSize','delay','isHalted')
        return dict(source='Questrade API',currency='USD',captured_at=data['captured_at'],
            position_id=holding.get('position_id'),symbol=holding['symbol'],
            expiry=held['expiry'],strike=held['strike'],
            stock={k:data['stock'].get(k) for k in fields},
            held={k:held.get(k) for k in fields})
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        raise ValueError('The saved quotes changed or are unavailable. Reload the holding and reopen Close to review them.') from None


def purchase_price(account, symbol):
    currency='USD' if account=='LIRA' else 'CAD'
    try:
        basis=stock_basis.get(account,symbol,'USD')
    except ValueError:
        basis=stock_basis.get(account,symbol,currency)
    price=basis.get('priceUsd')
    if not isinstance(price,(int,float)) or isinstance(price,bool) or not 0 < price < float('inf'):
        raise ValueError('Save the original USD purchase price in dashboard Profile settings first.')
    return price

def opening_reference(account, symbol, held, shares, contracts, position_id=None, transaction=None):
    price=purchase_price(account,symbol)
    if position_id:
        saved=covered_positions.history(position_id,db=transaction)
        history=position_history.resolve(account,symbol,held,contracts,[saved['opening']] if saved['opening'] else [],saved['rollovers'])
        # A position owns its original sale even while its rollover chain is incomplete.
        # Display that receipt without treating it as the net cash for the current call.
        if saved['opening']:
            opening=saved['opening']
            history.update(option_total_usd=opening['price_usd']*opening['contracts']*100,
                           option_price_usd=opening['price_usd'],option_settlement_date=opening['settlement_date'],
                           original_option_expiry=opening['expiry'],original_option_strike=opening['strike'],
                           opening_record_id=opening['id'])
            if history['history_status']=='incomplete' and history['history_note'].startswith('Record exactly one original opening'):
                history['history_note']='The original opening sale is recorded, but the rollover history does not yet connect it to the current call. Record each missing rollover to calculate cumulative P/L.'
        history.update(covered_positions.prior_realized(position_id,db=transaction))
        if not saved['opening'] and history.get('realized_sources'):
            history['history_note']='Earlier expired-call gains are recorded. Record the current call’s opening sale and any rollovers to complete its P/L.'
    else:
        history=position_history.resolve(account, symbol, held, contracts,
            option_premiums.records()+option_premiums.usd_records(), option_rollovers.records())
    currency='USD' if account=='LIRA' else 'CAD'
    try:
        basis=stock_basis.get(account,symbol,'USD')
    except ValueError:
        basis=stock_basis.get(account,symbol,currency)
    stock_fees=(basis.get('feesUsd') or 0)*shares/basis['quantity']
    own=saved.get('position',{}).get('stock_purchase') if position_id else None
    if own:
        price=own['priceUsd'];stock_fees=(own.get('feesUsd') or 0)*shares/own['quantity']
    reference=dict(stock_price_usd=price, stock_total_usd=price*shares,
                   stock_cost_usd=price*shares+stock_fees, stock_fees_usd=stock_fees,
                   option_total_usd=None, option_price_usd=None,
                   source='Saved USD purchase price and proportional purchase fees; opening sale plus linked rollovers, each counted once')
    reference.update(history)
    return reference


def reaccount_capture(capture):
    """Use current transaction records with saved quotes; no market refresh or file write."""
    import copy
    result=copy.deepcopy(capture)
    data=result.get('inputs', {})
    if not {'account','symbol','held','shares','contracts'} <= data.keys() or not {'expiry','strike'} <= data['held'].keys() or 'result' not in result:
        return result
    data['opening_reference']=opening_reference(data['account'],data['symbol'],data['held'],data['shares'],data['contracts'],data.get('position_id'))
    model.apply_accounting(data, result['result'])
    return result

def with_interest_rate(data, selection=None):
    import copy
    result=copy.deepcopy(data)
    if selection is not None or not result.get('interest_rate'):
        result['interest_rate']=interest_rates.resolve(selection, result['held']['expiry'], result['as_of'])
    return result


def with_rollover_criteria(data, selection=None, check_coverage=True):
    import copy
    result=copy.deepcopy(data)
    criteria=model.normalize_criteria(selection if selection is not None else data.get('rollover_criteria'))
    result['rollover_criteria']=criteria
    if check_coverage:
        coverage=data.get('candidate_coverage',dict(minimum_strike=1.2*data['initial_purchase_price_usd'],maximum_strike=None))
        spot=(data['stock']['bidPrice']+data['stock']['askPrice'])/2
        requested=model.strike_bounds(data['initial_purchase_price_usd'],spot,**criteria)
        if requested['minimum_strike']<coverage['minimum_strike']-1e-8 or (coverage.get('maximum_strike') is not None and (requested['maximum_strike'] is None or requested['maximum_strike']>coverage['maximum_strike']+1e-8)):
            raise ValueError('The selected strike range extends beyond the saved quotes. Use Refresh data & analyze to retrieve the additional contracts.')
    return result


def scenario(request):
    account=request.get('account');symbol=request.get('symbol')
    select_holding(request)
    capture=load_capture(request)
    if capture is None: raise ValueError('Refresh data & analyze this position first.')
    original=with_interest_rate(capture['inputs'],request.get('interest_rate'))
    rate=original['interest_rate']['rate']
    inputs=model.stock_price_scenario(original,request.get('stock_price'),rate=rate)
    inputs=with_rollover_criteria(inputs,request.get('rollover_criteria'))
    at_capture=abs(request['stock_price']-(original['stock']['bidPrice']+original['stock']['askPrice'])/2)<1e-8
    result=model.evaluate(inputs, rate=rate, close_at_mid=at_capture, **inputs['rollover_criteria'])
    return dict(inputs=inputs,result=result,scenario=dict(stock_price=request['stock_price'],
                captured_stock_price=(original['stock']['bidPrice']+original['stock']['askPrice'])/2,
                note='Hypothetical stock price; options repriced at captured implied volatility and spreads. No new market quotes fetched.'))

def run(request):
    account=request.get('account','RRSP'); symbol=request.get('symbol','ASTS')
    p=select_holding(dict(request,account=account,symbol=symbol)); horizon=request.get('horizon',30)
    if p.get('call_contracts')==0:raise ValueError('Record the option opening sale for this stock holding before analyzing covered calls.')
    if p.get('can_mark_expired'):raise ValueError('Complete this historical call’s buyback/rollover or actual expiry record before refreshing current quotes.')
    initial_purchase=p['stock_purchase']['priceUsd'] if p.get('stock_purchase') else purchase_price(account,symbol)
    if type(horizon) is not int or not 1<=horizon<=63: raise ValueError('Invalid horizon')
    criteria=model.normalize_criteria(request.get('rollover_criteria'))
    today=datetime.now(ZoneInfo('America/Vancouver')).date()
    saved_refresh_token(ROOT/'.secrets/questrade.json')
    try:
        history_response=public_fetch('https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe='')+'?range=3mo&interval=1d')['chart']['result'][0]
    except HTTPError as error:
        raise StockHistoryUnavailable(f'Stock price history is unavailable from Yahoo Finance (HTTP {error.code}).') from None
    except (URLError,OSError,ValueError,KeyError,IndexError,TypeError):
        raise StockHistoryUnavailable('Stock price history is unavailable from Yahoo Finance. Try refreshing later.') from None
    if history_response['meta']['currency']!='USD' or history_response['meta']['symbol']!=symbol: raise ValueError('Requires USD stock history')
    history=[dict(date=datetime.fromtimestamp(t,timezone.utc).date().isoformat(),close=c)
             for t,c in zip(history_response['timestamp'],history_response['indicators']['quote'][0]['close']) if c is not None]
    base,token=authorize(ROOT/'.secrets/questrade.json')
    api=lambda route:fetch(base+route,token)
    options=lambda ids:fetch(base+'markets/quotes/options',token,json_body={'optionIds':ids})
    found=[s for s in api('symbols/search?'+urlencode({'prefix':symbol}))['symbols'] if s['symbol']==symbol and s.get('isTradable')]
    if len(found)!=1: raise ValueError('Underlying is ambiguous')
    sid=found[0]['symbolId'];chain=api(f'symbols/{sid}/options');old_id=call_id(chain,p)
    stock=next(q for q in api('markets/quotes?'+urlencode({'ids':sid}))['quotes'] if q['symbolId']==sid)
    expiry=model.date.fromisoformat(p['call_expiry']);strike=float(p['call_strike_native_currency'])
    listed=listed_calls(chain,p,(today+timedelta(days=1)).isoformat(),model.month_shift(expiry,12).isoformat(),criteria['purchase_price_multiplier']*initial_purchase,float('inf'))
    listed={oid:record for oid,record in listed.items() if record['strike']>=criteria['purchase_price_multiplier']*initial_purchase}
    listed[old_id]=dict(strike=strike,expiry=p['call_expiry'],symbol_id=old_id)
    quotes={};candidates=[]
    ids=sorted(listed)
    for start in range(0,len(ids),50):
        batch=ids[start:start+50]
        details={d['symbolId']:d for d in api('symbols?'+urlencode({'ids':','.join(map(str,batch))}))['symbols']}
        valid=[]
        for oid in batch:
            record=listed[oid]
            try: validate_contract(details[oid],dict(p,call_expiry=record['expiry'],call_strike_native_currency=str(record['strike'])),sid)
            except (ImporterError,KeyError,ValueError): continue
            valid.append(oid)
        if not valid: continue
        response=options(valid)
        for q in response.get('optionQuotes',response.get('quotes',[])):
            oid=q['symbolId'];quotes[oid]=dict(listed[oid],**metrics(q),validated=True)
    if old_id not in quotes: raise ValueError('Held option quote unavailable')
    captured=datetime.now(timezone.utc).isoformat()
    data=dict(initial_purchase_price_usd=initial_purchase,as_of=today.isoformat(),account=account,symbol=symbol,shares=p['shares'],contracts=p['call_contracts'],stock=metrics(stock),held=quotes[old_id],history=history,candidates=[q for oid,q in quotes.items() if oid!=old_id],captured_at=captured,
              sources=dict(purchase_price='Database stock_cost_basis.price_usd for this account and symbol',history='Yahoo Finance daily closes (unadjusted)',options='Questrade API verified listed standard calls',future_prices='Return bootstrap + midpoint-calibrated constant-volatility call approximation'))
    data['rollover_criteria']=criteria
    data['candidate_coverage']=dict(minimum_strike=criteria['purchase_price_multiplier']*initial_purchase,maximum_strike=None)
    data['position_id']=p['position_id']
    data['opening_reference']=opening_reference(account,symbol,data['held'],data['shares'],data['contracts'],data['position_id'])
    data=with_interest_rate(data,request.get('interest_rate'))
    result=model.evaluate(data,horizon=horizon,rate=data['interest_rate']['rate'],**criteria)
    output=dict(inputs=data,result=result)
    target=capture_path(account,symbol,p['position_id'])
    temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(output,indent=2));temporary.replace(target)
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--account',default='RRSP');parser.add_argument('--symbol',default='ASTS');args=parser.parse_args()
    try:
        result=run(vars(args));print(f"Saved {len(result['result']['rows'])} strategy comparisons")
    except Exception as error:
        print(f'Analysis unavailable: {str(error) if isinstance(error,(ValueError,ImporterError)) else "Market-data request failed; previous capture retained"}')
        raise SystemExit(1)
