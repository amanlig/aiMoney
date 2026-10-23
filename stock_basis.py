"""Shared persistent stock cost basis for dashboard, simulation and assessments."""
from database_schema import SCHEMA
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re
from database import connect as database_connect
from fx_samples import DB, connect as sample_connect


def connect(path=DB):
    db=sample_connect(path)
    db.execute(SCHEMA['stock_cost_basis'])
    return db


def record(row):
    value=dict(row)
    return dict(id=value['id'],account=value['account'],symbol=value['symbol'],currency=value['currency'],
                date=value['purchase_date'],quantity=value['quantity'],priceUsd=value['price_usd'],
                feesUsd=value['fees_usd'],fx=value['purchase_fx'],cadTotal=value['total_cost'] if value['currency']=='CAD' else None,
                totalCost=value['total_cost'],averageCost=value['total_cost']/value['quantity'],updated_at=value['updated_at'])


def records(path=DB):
    with connect(path) as db:return [record(r) for r in db.execute('SELECT * FROM stock_cost_basis ORDER BY account,symbol')]


def get(account,symbol,currency='CAD',path=DB):
    with database_connect(path, readonly=True) as db:
        row=db.execute('SELECT * FROM stock_cost_basis WHERE account=? AND symbol=? AND currency=?',(account,symbol,currency)).fetchone()
    if row is None:raise ValueError(f'No saved stock cost basis for {account} {symbol}. Save it in Profile settings.')
    return record(row)


def validate(data):
    if not isinstance(data,dict):raise ValueError('Expected a cost-basis record.')
    value=dict(data)
    if value.get('account') not in ['RRSP','TFSA','LIRA'] or value.get('currency') not in ['CAD','USD']:
        raise ValueError('Choose a supported account and currency.')
    value['symbol']=str(value.get('symbol','')).strip().upper()
    if not re.fullmatch(r'[A-Z0-9.\-]{1,20}',value['symbol']):raise ValueError('Enter a ticker.')
    for key in ['quantity','totalCost','priceUsd','feesUsd','fx']:
        x=value.get(key)
        if key=='totalCost' and x is None:x=value.get('cadTotal')
        if x is None and key not in ['quantity','totalCost']:
            value[key]=None;continue
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 or (key!='feesUsd' and x==0):
            raise ValueError(f'Enter a valid {key}.')
        value[key]=x
    day=value.get('date')
    value['date']=date.fromisoformat(day).isoformat() if day else None
    if value['date'] and value['date']>date.today().isoformat():raise ValueError('Purchase date cannot be in the future.')
    if value['priceUsd'] is not None and value['feesUsd'] is not None and (value['currency']=='USD' or value['fx'] is not None):
        usd=value['quantity']*value['priceUsd']+value['feesUsd']
        expected=usd*(value['fx'] if value['currency']=='CAD' else 1)
        if abs(value['totalCost']-expected)>max(.10,usd*.000051):raise ValueError('Stock cost does not reconcile with quantity, price, fees and purchase FX.')
    return value


def save_many(items,path=DB,insert_only=False):
    if not isinstance(items,list) or len(items)>100:raise ValueError('Expected up to 100 cost-basis records.')
    values=[validate(item) for item in items]
    if len({(v['account'],v['symbol'],v['currency']) for v in values})!=len(values):raise ValueError('Duplicate holdings in cost-basis request.')
    with connect(path) as db:
        for v in values:
            sql='''INSERT INTO stock_cost_basis (account,symbol,currency,purchase_date,quantity,price_usd,fees_usd,purchase_fx,total_cost,updated_at)
              VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account,symbol,currency) '''
            sql+='DO NOTHING' if insert_only else '''DO UPDATE SET purchase_date=excluded.purchase_date,quantity=excluded.quantity,
              price_usd=excluded.price_usd,fees_usd=excluded.fees_usd,purchase_fx=excluded.purchase_fx,total_cost=excluded.total_cost,updated_at=excluded.updated_at'''
            db.execute(sql,(v['account'],v['symbol'],v['currency'],v['date'],v['quantity'],v['priceUsd'],v['feesUsd'],v['fx'],v['totalCost'],datetime.now(timezone.utc).isoformat()))
    return records(path)


def migrate(path=DB,source=None):
    source=source or Path(__file__).resolve().parent/'data/cost-basis-defaults.json'
    values=json.loads(source.read_text()) if source.exists() else []
    return save_many([dict(v,currency='CAD',totalCost=v['cadTotal']) for v in values],path,insert_only=True)


if __name__=='__main__':
    for value in migrate():print(value['account'],value['symbol'],value['averageCost'])
