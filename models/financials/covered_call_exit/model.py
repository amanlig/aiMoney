"""Independent covered-call scenario ranking. Python standard library only."""
import calendar
from datetime import date, timedelta
import math
import random
import statistics

VERSION = '1.10'

def month_shift(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))

def call_price(spot, strike, years, volatility, rate=0.04):
    if years <= 0:
        return max(spot-strike, 0)
    if volatility <= 0:
        return max(spot-strike*math.exp(-rate*years), 0)
    n = lambda x: (1+math.erf(x/math.sqrt(2)))/2
    d1 = (math.log(spot/strike)+(rate+volatility**2/2)*years)/(volatility*math.sqrt(years))
    return spot*n(d1)-strike*math.exp(-rate*years)*n(d1-volatility*math.sqrt(years))

def implied_volatility(spot, strike, years, price, rate):
    if not max(spot-strike*math.exp(-rate*years), 0) < price < spot:
        raise ValueError('Option midpoint cannot calibrate this pricing approximation')
    low, high = 0.0001, 8.0
    for _ in range(70):
        mid=(low+high)/2
        if call_price(spot,strike,years,mid,rate)<price: low=mid
        else: high=mid
    return (low+high)/2

def valid_quote(q, contracts, option=True):
    bid, ask=q.get('bidPrice'),q.get('askPrice')
    return (all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in (bid,ask))
            and 0 < bid <= ask and q.get('delay') == 0 and q.get('isHalted') is False
            and (not option or (q.get('bidSize') or 0)>=contracts and (q.get('askSize') or 0)>=contracts))

def summarize(values, baseline, discount):
    values=sorted(v*discount for v in values)
    return dict(mean=sum(values)/len(values), p10=values[int(.1*(len(values)-1))],
                p90=values[int(.9*(len(values)-1))], probability_beating_close=sum(v>baseline for v in values)/len(values))

def evaluate(data, horizon=30, paths=600, seed=42, rate=0.04):
    """Compare discounted USD liquidation wealth at a common trading-day horizon.

    Historical daily log returns are sampled with replacement. Future option
    marks use constant midpoint-implied volatility and today's absolute spread.
    No pathwise foresight or optimal-stopping claims. Rolled positions close at
    the same horizon; expiration settlement is modelled, early exercise is not.
    """
    if type(horizon) is not int or not 1<=horizon<=63 or type(paths) is not int or not 100<=paths<=5000:
        raise ValueError('Use 1–63 trading days and 100–5000 paths')
    if not math.isfinite(rate) or not -.1<=rate<=.3:
        raise ValueError('Invalid interest rate')
    today=date.fromisoformat(data['as_of'][:10]); held=data['held']; expiry=date.fromisoformat(held['expiry'])
    n=data['contracts']; shares=data['shares']; strike=held['strike']
    purchase=data.get('initial_purchase_price_usd')
    if not isinstance(purchase,(int,float)) or isinstance(purchase,bool) or not math.isfinite(purchase) or purchase<=0:
        raise ValueError('A positive original USD purchase price is required')
    floor=purchase*1.10
    if type(n) is not int or n<=0 or shares!=100*n or strike<=0 or expiry<=today:
        raise ValueError('Requires an unexpired, fully covered standard 100-share call position')
    if not valid_quote(held,n) or not valid_quote(data['stock'],n,False):
        raise ValueError('Fresh, non-halted, two-sided quotes and full option size are required')
    history=data['history']; start=month_shift(today,-3)
    history=sorted((r for r in history if start<=date.fromisoformat(r['date'])<today),key=lambda r:r['date'])
    if len(history)<40 or len({r['date'] for r in history})!=len(history):
        raise ValueError('At least 40 unique completed daily closes in the last three months are required')
    closes=[float(r['close']) for r in history]
    if not all(math.isfinite(x) and x>0 for x in closes): raise ValueError('Invalid stock history')
    if (today-date.fromisoformat(history[-1]['date'])).days>5: raise ValueError('Stock history is stale')
    returns=[math.log(b/a) for a,b in zip(closes,closes[1:])]
    stock=data['stock']; spot=(stock['bidPrice']+stock['askPrice'])/2
    spread=(stock['askPrice']-stock['bidPrice'])/2
    held_iv=held.get('scenario_iv') or implied_volatility(spot,strike,(expiry-today).days/365,(held['bidPrice']+held['askPrice'])/2,rate)
    baseline=shares*stock['bidPrice']-n*100*held['askPrice']
    rng=random.Random(seed); trajectories=[]
    for _ in range(paths):
        s=spot; path=[]
        for day in range(horizon): s*=math.exp(rng.choice(returns)); path.append(s)
        trajectories.append(path)
    rows=[dict(strategy='Close now',days=0,mean=baseline,p10=baseline,p90=baseline,probability_beating_close=0,improvement=0, cash_flows=dict(stock_sale=shares*stock['bidPrice'],option_purchase=-n*100*held['askPrice'],option_sale=0),eligible=stock['bidPrice']>=floor,sale_floor_pass_rate=float(stock['bidPrice']>=floor))]
    def liquidation(path, days, k, exp, iv, halfspread):
        expiry_steps=max(1,math.ceil((exp-today).days*252/365))
        if expiry_steps<=days:
            s=path[expiry_steps-1]
            # Cash assignment above strike; below strike retain then sell shares.
            growth=math.exp(rate*(days-expiry_steps)/252)
            return (k if s>=k else max(0,path[days-1]-spread)), dict(stock_sale=n*100*k*growth if s>=k else shares*max(0,path[days-1]-spread),option_purchase=0,option_sale=0)
        s=path[days-1]; remaining=max(0,((exp-today).days-days*365/252)/365)
        return max(0,s-spread), dict(stock_sale=shares*max(0,s-spread),option_purchase=-n*100*(call_price(s,k,remaining,iv,rate)+halfspread),option_sale=0)
    def aggregate(outcomes,discount):
        prices=[price for price,flow in outcomes]
        flows=[flow for price,flow in outcomes]
        stats=summarize([sum(f.values()) for f in flows],baseline,discount)
        stats['sale_floor_pass_rate']=sum(price>=floor for price in prices)/len(prices)
        stats['eligible']=all(price>=floor for price in prices)
        stats['cash_flows']={key:sum(f[key] for f in flows)*discount/len(flows) for key in flows[0]}
        return stats
    for days in sorted({1,min(5,horizon),min(10,horizon),min(21,horizon),horizon}):
        stats=aggregate([liquidation(p,days,strike,expiry,held_iv,(held['askPrice']-held['bidPrice'])/2) for p in trajectories],math.exp(-rate*days/252))
        rows.append(dict(strategy='Wait then close',days=days,improvement=stats['mean']-baseline,**stats))
    excluded=0
    for q in data.get('candidates',[]):
        exp=date.fromisoformat(q['expiry']); k=q['strike']
        if not (k>=1.2*purchase and k>spot and today<exp<=month_shift(expiry,12) and exp>today and (exp!=expiry or k!=strike)) or not valid_quote(q,n) or q.get('validated') is not True:
            excluded+=1;continue
        try: iv=q.get('scenario_iv') or implied_volatility(spot,k,(exp-today).days/365,(q['bidPrice']+q['askPrice'])/2,rate)
        except ValueError: excluded+=1;continue
        credit=n*100*(q['bidPrice']-held['askPrice'])
        discount=math.exp(-rate*horizon/252)
        flows=[liquidation(p,horizon,k,exp,iv,(q['askPrice']-q['bidPrice'])/2) for p in trajectories]
        for price,flow in flows:
            flow['option_purchase']-=n*100*held['askPrice']/discount
            flow['option_sale']+=n*100*q['bidPrice']/discount
        stats=aggregate(flows,discount)
        stats['eligible']=stats['eligible'] and k>=floor
        rows.append(dict(strategy='Roll then close',days=horizon,strike=k,expiry=exp.isoformat(),roll_credit=credit,roll_funding=rollover_funding(data,q),improvement=stats['mean']-baseline,**stats))
    for row in rows:
        if row['strategy']=='Roll then close':
            quote=next(q for q in data['candidates'] if q['expiry']==row['expiry'] and q['strike']==row['strike'])
            row['expire_worthless']=expire_worthless_outcome(data,quote)
    reference=data.get('opening_reference',{})
    stock_cost=reference.get('stock_total_usd');premium=reference.get('option_total_usd')
    known=all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (stock_cost,premium))
    for row in rows:
        row['net_profit_usd']=row['mean']+premium-stock_cost if known else None
    rows.sort(key=lambda r:(r['eligible'],r['mean']),reverse=True)
    top_choices=sorted((row for row in rows if row['strategy']=='Roll then close' and row['net_profit_usd'] is not None),
                       key=lambda row:row['net_profit_usd'],reverse=True)[:3]

    return dict(version=VERSION,top_choices=top_choices,profit_reference_available=known,
                search=dict(minimum_strike=max(1.2*purchase,spot),minimum_exclusive=spot>=1.2*purchase,maximum_strike=None,first_expiry=(today+timedelta(days=1)).isoformat(),last_expiry=month_shift(expiry,12).isoformat()),initial_purchase_price_usd=purchase,minimum_stock_sale_price_usd=floor,
                constraint='Rank the three best net profits regardless of profit sign or sale-floor eligibility. Sale-floor flags remain visible; strike/expiry and quote-quality filters remain enforced. Future market prices are not guaranteed.',rows=rows,baseline=baseline,excluded=excluded,paths=paths,seed=seed,
                history_count=len(closes),history_start=history[0]['date'],history_end=history[-1]['date'],
                realized_volatility=statistics.stdev(returns)*math.sqrt(252),held_implied_volatility=held_iv,
                objective='Highest simulated mean discounted USD liquidation wealth; not a validated profit forecast',
                assumptions=['Three-month daily-return bootstrap; historical drift retained', 'Constant calibrated volatility; European call approximation; no dividends or early assignment',
                "Today's spreads held constant; fees excluded; no taxes; USD retained", 'Rollover credit is cash received, not profit; remaining option liability is deducted at the common horizon',
                'No historical option-chain backtest; probabilities describe model paths only'])


def stock_price_scenario(data, price, rate=0.04):
    """Reprice a captured chain at a hypothetical spot with fixed calibrated IV.

    Preserves original spreads and snapshot data; performs no network calls.
    At the captured midpoint the original quotes are returned unchanged.
    """
    import copy
    if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price):
        raise ValueError('Enter a finite hypothetical stock price')
    original=(data['stock']['bidPrice']+data['stock']['askPrice'])/2
    if not .5*original<=price<=1.5*original:
        raise ValueError('Hypothetical stock price must be within ±50% of the captured midpoint')
    result=copy.deepcopy(data)
    if abs(price-original)<1e-9:return result
    today=date.fromisoformat(data['as_of'][:10])
    half=(data['stock']['askPrice']-data['stock']['bidPrice'])/2
    result['stock'].update(bidPrice=max(.000001,price-half),askPrice=price+half)
    for quote in [result['held']]+result.get('candidates',[]):
        if not valid_quote(quote,data['contracts']):continue
        years=(date.fromisoformat(quote['expiry'])-today).days/365
        if years<=0:continue
        try:iv=implied_volatility(original,quote['strike'],years,(quote['bidPrice']+quote['askPrice'])/2,rate)
        except ValueError:continue
        halfspread=(quote['askPrice']-quote['bidPrice'])/2
        mid=call_price(price,quote['strike'],years,iv,rate)
        quote.update(bidPrice=max(.000001,mid-halfspread),askPrice=mid+halfspread,scenario_iv=iv)
    return result


def expire_worthless_outcome(data, replacement):
    """Conditional option-only result, not a prediction or full stock liquidation.

    The held call is bought back and replacement sold now. Assume the replacement
    later expires worthless with no early assignment and all shares retained.
    No future cash flow is discounted: both nonzero cash flows occur now.
    """
    count=data['contracts']*100
    original_buyback=count*data['held']['askPrice']
    new_premium=count*replacement['bidPrice']
    net_cash=new_premium-original_buyback
    original_premium=data.get('opening_reference',{}).get('option_total_usd')
    option_profit=original_premium+net_cash if isinstance(original_premium,(int,float)) and not isinstance(original_premium,bool) and math.isfinite(original_premium) else None
    return dict(strategy='Roll then expire worthless',exit_mode='expire',days=None,
                expiry=replacement['expiry'],strike=replacement['strike'],mean=net_cash,
                cash_flows=dict(stock_sale=0,option_purchase=-original_buyback,option_sale=new_premium),
                stock_retained=data['shares'],replacement_buyback_usd=0,held_buyback_usd=original_buyback,
                option_profit_usd=option_profit,net_profit_usd=None,
                roll_funding=rollover_funding(data,replacement),assumption='Conditional on replacement call expiring worthless with no assignment; stock retained, stock gain/loss excluded.')


def rollover_funding(data, replacement):
    """Gross USD rollover debit, not broker margin or an additional-deposit quote."""
    multiplier=data['contracts']*100
    buyback=multiplier*data['held']['askPrice']
    premium=multiplier*replacement['bidPrice']
    return dict(held_buyback_usd=buyback,replacement_premium_usd=premium,
                net_debit_usd=max(0,buyback-premium),net_credit_usd=max(0,premium-buyback),
                note='Estimated net rollover debit before fees, assuming simultaneous legs. Does not measure broker buying power, account cash shortfall or margin requirement.')
