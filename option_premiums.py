"""Reviewed opening call premiums stored separately from FX training samples."""
from database_schema import SCHEMA
from datetime import date, datetime, timezone
import math
import re
from database import connect as database_connect, INTEGRITY_ERRORS
from fx_samples import DB, connect as sample_connect


def connect(path=DB):
    db=sample_connect(path)
    db.execute(SCHEMA['option_premiums'])
    return db


def records(path=DB):
    with connect(path) as db:
        return [dict(r) for r in db.execute('SELECT * FROM option_premiums ORDER BY settlement_date DESC,id DESC')]


def save(data,path=DB, *, record_id=None):
    if not isinstance(data,dict) or data.get('reviewed') is not True:
        raise ValueError('Review the opening premium confirmation before saving.')
    value={k:data.get(k) for k in ['account','symbol','expiry','strike','contracts','settlement_date','price_usd','fees_usd','fx','net_cad']}
    if value['account'] not in ['RRSP','TFSA','LIRA']:
        raise ValueError('Choose an account.')
    value['symbol']=str(value['symbol'] or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9.\-]{1,20}',value['symbol']):
        raise ValueError('Enter a ticker.')
    for key in ['expiry','settlement_date']:
        value[key]=date.fromisoformat(value[key]).isoformat()
    if value['settlement_date']>date.today().isoformat() or value['settlement_date']>value['expiry']:
        raise ValueError('Check settlement date and expiry.')
    if type(value['contracts']) is not int or value['contracts']<=0:
        raise ValueError('Enter a positive whole number of contracts.')
    for key in ['strike','price_usd','fees_usd','fx','net_cad']:
        x=value[key]
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 or (key!='fees_usd' and x==0):
            raise ValueError(f'Enter a valid {key}.')
    value['net_usd']=round(value['contracts']*100*value['price_usd']-value['fees_usd'],2)
    if value['net_usd']<=0 or abs(value['net_usd']*value['fx']-value['net_cad'])>max(.10,value['net_usd']*.000051):
        raise ValueError('Net CAD must reconcile with contracts × 100 × premium, less USD fees, converted at the confirmation FX.')
    for r in usd_records(path):
        if all(r[key]==value[key] for key in ['account','symbol','expiry','strike','contracts','settlement_date']):
            raise ValueError('This opening premium is already recorded.')
    value['created_at']=datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        try:
            columns=list(value)
            if record_id is None:
                record_id=db.insert_id(f'INSERT INTO option_premiums ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',[value[k] for k in columns])
            else:
                if not db.execute('SELECT id FROM option_premiums WHERE id=?',(record_id,)).fetchone():
                    raise ValueError('Opening premium not found.')
                db.execute('UPDATE option_premiums SET '+','.join(k+'=?' for k in columns if k!='created_at')+' WHERE id=?',[value[k] for k in columns if k!='created_at']+[record_id])
        except INTEGRITY_ERRORS:
            raise ValueError('This opening premium is already recorded.') from None
        return dict(db.execute('SELECT * FROM option_premiums WHERE id=?',(record_id,)).fetchone())


def usd_records(path=DB):
    """USD-only confirmations; legacy converted confirmations remain unchanged."""
    with connect(path) as db:
        exists=db.table_exists('option_premium_sales_usd')
        return [dict(r) for r in db.execute('SELECT * FROM option_premium_sales_usd ORDER BY settlement_date DESC,id DESC')] if exists else []


def save_usd(data,path=DB, *, record_id=None):
    if not isinstance(data,dict) or data.get('reviewed') is not True:
        raise ValueError('Verify the option sale against your confirmation before saving.')
    account=data.get('account');symbol=str(data.get('symbol','')).strip().upper()
    if account not in ['RRSP','TFSA','LIRA'] or not re.fullmatch(r'[A-Z0-9.\-]{1,20}',symbol):
        raise ValueError('Choose a valid account and ticker.')
    expiry=date.fromisoformat(data['expiry']).isoformat()
    settlement=date.fromisoformat(data['settlement_date']).isoformat()
    if settlement>date.today().isoformat() or settlement>expiry:
        raise ValueError('Check settlement date and expiration.')
    contracts=data.get('contracts')
    if type(contracts) is not int or contracts<=0:
        raise ValueError('Enter a positive whole number of contracts.')
    for key in ['strike','price_usd']:
        value=data.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError(f'Enter a positive {key}.')
    strike=data['strike'];price=data['price_usd'];gross=round(price*contracts*100,2)
    if not math.isfinite(gross):raise ValueError('Premium is too large.')
    # Check both formats to avoid recording the same confirmation twice.
    for r in records(path)+[r for r in usd_records(path) if r['id'] != record_id]:
        if (r['account'],r['symbol'],r['expiry'],r['strike'],r['contracts'],r['settlement_date'])==(account,symbol,expiry,strike,contracts,settlement):
            raise ValueError('This opening premium is already recorded.')
    with connect(path) as db:
        db.execute(SCHEMA['option_premium_sales_usd'])
        try:
            if record_id is not None:
                if not db.execute('SELECT id FROM option_premium_sales_usd WHERE id=?',(record_id,)).fetchone():
                    raise ValueError('Opening premium not found.')
                db.execute('UPDATE option_premium_sales_usd SET account=?,symbol=?,expiry=?,strike=?,contracts=?,settlement_date=?,price_usd=?,gross_usd=? WHERE id=?',(account,symbol,expiry,strike,contracts,settlement,price,gross,record_id))
            else:
                record_id=db.insert_id('''INSERT INTO option_premium_sales_usd
              (account,symbol,expiry,strike,contracts,settlement_date,price_usd,gross_usd,created_at)
              VALUES (?,?,?,?,?,?,?,?,?)''',(account,symbol,expiry,strike,contracts,settlement,price,gross,datetime.now(timezone.utc).isoformat()))
        except INTEGRITY_ERRORS:
            raise ValueError('This opening premium is already recorded.') from None
        return dict(db.execute('SELECT * FROM option_premium_sales_usd WHERE id=?',(record_id,)).fetchone())
