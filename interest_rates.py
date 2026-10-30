"""Application-owned Treasury data access; the independent model stays offline."""
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import threading
import time
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

SOURCE_URL = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve'
FEED_URL = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}'
CACHE = Path(__file__).resolve().parent/'data/treasury-yield-curve.json'
TENORS = {'BC_1MONTH': 1/12, 'BC_1_5MONTH': 1.5/12, 'BC_2MONTH': 2/12,
          'BC_3MONTH': .25, 'BC_4MONTH': 1/3, 'BC_6MONTH': .5,
          **{f'BC_{n}YEAR': n for n in (1, 2, 3, 5, 7, 10, 20, 30)}}
LOCK = threading.Lock()
_last_attempt = 0


class RateUnavailable(ValueError):
    pass


def today():
    return datetime.now(ZoneInfo('America/Vancouver')).date()


def annual_rate(percent):
    if isinstance(percent, bool) or not isinstance(percent, (int, float)) or not math.isfinite(percent) or not -5 <= percent <= 25:
        raise ValueError('Enter an annual interest yield between -5% and 25%.')
    # Treasury CMTs are nominal annual bond-equivalent yields (semiannual).
    return 2*math.log1p(percent/200)


def parse_curve(payload, as_of):
    rows=[]
    try:
        root=ET.fromstring(payload)
        for entry in root.iter():
            if entry.tag.rsplit('}',1)[-1] != 'properties': continue
            fields={n.tag.rsplit('}',1)[-1]: n.text for n in entry}
            observed=date.fromisoformat(fields.get('NEW_DATE','')[:10])
            if observed > as_of: continue
            points=[]
            for field, years in TENORS.items():
                text=fields.get(field)
                if text is None: continue
                value=float(text)
                annual_rate(value)
                points.append(dict(years=years, annual_percent=value))
            if len(points)>=2:
                rows.append(dict(observed_on=observed.isoformat(), points=sorted(points,key=lambda p:p['years'])))
    except (ET.ParseError, ValueError, TypeError) as error:
        raise RateUnavailable('Treasury returned invalid yield-curve data.') from None
    if not rows: raise RateUnavailable('Treasury has no usable published yield curve.')
    return max(rows,key=lambda r:r['observed_on'])


def usable(curve, as_of):
    try:
        age=(as_of-date.fromisoformat(curve['observed_on'])).days
        points=curve['points']
        return 0<=age<=7 and len(points)>=2 and all(
            math.isfinite(p['years']) and p['years']>0 and annual_rate(p['annual_percent']) is not None for p in points)
    except (KeyError, TypeError, ValueError):
        return False


def latest_curve():
    global _last_attempt
    as_of=today()
    with LOCK:
        try: cached=json.loads(CACHE.read_text())
        except (OSError,ValueError): cached=None
        good=usable(cached,as_of)
        if good and time.time()-cached.get('retrieved_epoch',0)<3600:
            return cached
        if time.time()-_last_attempt<300:
            if good: return {**cached,'warning':'Treasury refresh unavailable; using the last published cached curve.'}
            raise RateUnavailable('Treasury rates are unavailable. Try again later or choose a manual interest rate in Settings.')
        _last_attempt=time.time()
        try:
            # Previous year is needed during the first days of January.
            curves=[]
            years=[as_of.year] + ([as_of.year-1] if as_of.month==1 and as_of.day<=7 else [])
            for year in years:
                url=FEED_URL.format(year=year)
                request=Request(url,headers={'User-Agent':'aiMoney/1.0','Accept':'application/xml'})
                with urlopen(request,timeout=12) as response:
                    payload=response.read(4_000_001)
                if len(payload)>4_000_000: raise RateUnavailable('Treasury response is too large.')
                try:
                    curve=parse_curve(payload,as_of)
                    curve['feed_url']=url
                    curves.append(curve)
                except RateUnavailable:
                    if year != as_of.year or len(years)==1: raise
            curve=max(curves,key=lambda r:r['observed_on'])
            if not usable(curve,as_of): raise RateUnavailable('The latest Treasury curve is more than seven calendar days old.')
            curve.update(retrieved_epoch=time.time(),retrieved_at=datetime.now(timezone.utc).isoformat())
            CACHE.parent.mkdir(parents=True,exist_ok=True)
            temporary=CACHE.with_suffix('.tmp')
            temporary.write_text(json.dumps(curve,indent=2)+'\n');temporary.replace(CACHE)
            return curve
        except (OSError, ValueError, KeyError, TypeError):
            if good: return {**cached,'warning':'Treasury refresh unavailable; using the last published cached curve.'}
            raise RateUnavailable('Treasury rates are unavailable or stale. Try again later or choose a manual interest rate in Settings.') from None


def resolve(selection, expiry=None, valuation_date=None):
    selection=selection or {'mode':'treasury'}
    if not isinstance(selection,dict) or selection.get('mode') not in ('treasury','manual'):
        raise ValueError('Select Treasury default or a manual interest rate.')
    if selection['mode']=='manual':
        percent=selection.get('annual_percent')
        return dict(selection={'mode':'manual','annual_percent':percent},annual_percent=percent,
                    rate=annual_rate(percent),source='Manual override',source_url=None,observed_on=None,
                    compounding='Nominal annual yield with semiannual compounding; rate = 2 × ln(1 + yield / 200).')
    if not expiry: raise ValueError('Select a holding with an option expiry to match the Treasury maturity.')
    reference=date.fromisoformat(valuation_date) if valuation_date else today()
    years=(date.fromisoformat(expiry)-reference).days/365
    if years<=0: raise ValueError('Treasury matching requires an unexpired option.')
    curve=latest_curve();points=sorted(curve['points'],key=lambda p:p['years'])
    lower=max((p for p in points if p['years']<=years),key=lambda p:p['years'],default=points[0])
    upper=min((p for p in points if p['years']>=years),key=lambda p:p['years'],default=points[-1])
    a,b=lower['years'],upper['years']
    percent=lower['annual_percent'] if a==b else lower['annual_percent']+(upper['annual_percent']-lower['annual_percent'])*(years-a)/(b-a)
    return dict(selection={'mode':'treasury'},annual_percent=percent,rate=annual_rate(percent),
                source='U.S. Treasury Daily Par Yield Curve',source_url=SOURCE_URL,feed_url=curve['feed_url'],
                observed_on=curve['observed_on'],retrieved_at=curve['retrieved_at'],expiry=expiry,
                valuation_date=reference.isoformat(),remaining_years=years,lower_tenor_years=a,upper_tenor_years=b,
                maturity_method='Linear interpolation of par yields; nearest published tenor outside the curve.',
                compounding='Bond-equivalent yield converted using rate = 2 × ln(1 + yield / 200).',
                warning=curve.get('warning'),
                limitation='Single held-option maturity rate for all calls and discounting; par yield is a proxy, not a bootstrapped zero rate.')
