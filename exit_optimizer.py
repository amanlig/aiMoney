"""App adapter for the independent covered-call exit model; read-only market APIs."""
import argparse
from datetime import datetime, timezone, timedelta
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlencode, quote
from zoneinfo import ZoneInfo
from macro_data import fetch as public_fetch
from questrade_quotes import authorize, fetch, call_id, validate_contract, ImporterError
from market_details import metrics
import stock_basis
import option_premiums
from roll_candidates import INPUTS, listed_calls

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('covered_call_exit_model',ROOT/'models/financials/covered_call_exit/model.py')
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)

def holdings():
    result=[]
    for account,name in INPUTS.items():
        for p in json.loads((ROOT/'data'/name).read_text())['positions']:
            if p.get('call_contracts'):
                result.append(dict(account=account,**p))
    return result

def purchase_price(account, symbol):
    currency='USD' if account=='LIRA' else 'CAD'
    basis=stock_basis.get(account,symbol,currency)
    price=basis.get('priceUsd')
    if not isinstance(price,(int,float)) or isinstance(price,bool) or not 0 < price < float('inf'):
        raise ValueError('Save the original USD purchase price in dashboard Profile settings first.')
    return price

def opening_reference(account, symbol, held, shares, contracts):
    price=purchase_price(account,symbol)
    matches=[r for r in option_premiums.records()+option_premiums.usd_records() if r['account']==account and r['symbol']==symbol
             and r['expiry']==held['expiry'] and float(r['strike'])==float(held['strike']) and r['contracts']==contracts]
    premium=matches[0] if len(matches)==1 else None
    return dict(stock_price_usd=price,stock_total_usd=price*shares,
                option_price_usd=premium['price_usd'] if premium else None,
                option_total_usd=premium['price_usd']*contracts*100 if premium else None,
                option_settlement_date=premium['settlement_date'] if premium else None,
                source='SQLite stock_cost_basis and exact-match option_premiums or option_premium_sales_usd; gross amounts, fees excluded')

def scenario(request):
    account=request.get('account');symbol=request.get('symbol')
    if not any(p['account']==account and p['symbol']==symbol for p in holdings()):
        raise ValueError('Choose a saved holding')
    path=ROOT/'reports'/f'exit-optimizer-{account.lower()}-{symbol.lower()}.json'
    if not path.exists():raise ValueError('Refresh data & analyze first')
    capture=json.loads(path.read_text());original=capture['inputs']
    inputs=model.stock_price_scenario(original,request.get('stock_price'))
    result=model.evaluate(inputs)
    return dict(inputs=inputs,result=result,scenario=dict(stock_price=request['stock_price'],
                captured_stock_price=(original['stock']['bidPrice']+original['stock']['askPrice'])/2,
                note='Hypothetical stock price; options repriced at captured implied volatility and spreads. No new market quotes fetched.'))

def run(request):
    account=request.get('account','RRSP'); symbol=request.get('symbol','ASTS')
    matches=[p for p in holdings() if p['account']==account and p['symbol']==symbol]
    if len(matches)!=1: raise ValueError('Choose one saved covered-call holding')
    p=matches[0]; horizon=request.get('horizon',30)
    initial_purchase=purchase_price(account,symbol)
    if type(horizon) is not int or not 1<=horizon<=63: raise ValueError('Invalid horizon')
    today=datetime.now(ZoneInfo('America/Vancouver')).date()
    history_response=public_fetch('https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe='')+'?range=3mo&interval=1d')['chart']['result'][0]
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
    listed=listed_calls(chain,p,(today+timedelta(days=1)).isoformat(),model.month_shift(expiry,12).isoformat(),1.2*initial_purchase,float('inf'))
    listed={oid:record for oid,record in listed.items() if record['strike']>=1.2*initial_purchase}
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
              sources=dict(purchase_price='SQLite stock_cost_basis.price_usd for this account and symbol',history='Yahoo Finance daily closes (unadjusted)',options='Questrade API verified listed standard calls',future_prices='Return bootstrap + midpoint-calibrated constant-volatility call approximation'))
    data['opening_reference']=opening_reference(account,symbol,data['held'],data['shares'],data['contracts'])
    result=model.evaluate(data,horizon=horizon)
    output=dict(inputs=data,result=result)
    target=ROOT/'reports'/f'exit-optimizer-{account.lower()}-{symbol.lower()}.json'
    temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(output,indent=2));temporary.replace(target)
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--account',default='RRSP');parser.add_argument('--symbol',default='ASTS');args=parser.parse_args()
    try:
        result=run(vars(args));print(f"Saved {len(result['result']['rows'])} strategy comparisons")
    except Exception as error:
        print(f'Analysis unavailable: {str(error) if isinstance(error,(ValueError,ImporterError)) else "Market-data request failed; previous capture retained"}')
        raise SystemExit(1)
