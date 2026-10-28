"""Completed USD call rollovers: both trade legs persist in one atomic record."""
from datetime import date, datetime, timezone
import math
import re
from database import DB, connect, INTEGRITY_ERRORS
from database_schema import SCHEMA


def records(path=DB):
    with connect(path) as db:
        db.execute(SCHEMA['option_rollovers'])
        return [dict(r) for r in db.execute('SELECT * FROM option_rollovers ORDER BY settlement_date DESC,id DESC')]


def validate(data):
    if not isinstance(data, dict) or data.get('reviewed') is not True:
        raise ValueError('Verify both rollover legs against your trade confirmation.')
    fields = ['account', 'symbol', 'settlement_date', 'contracts', 'buyback_expiry', 'buyback_strike',
              'buyback_price_usd', 'sale_expiry', 'sale_strike', 'sale_price_usd', 'fees_usd']
    value = {key: data.get(key) for key in fields}
    value['symbol'] = str(value['symbol'] or '').strip().upper()
    if value['account'] not in ['RRSP', 'TFSA', 'LIRA'] or not re.fullmatch(r'[A-Z0-9.\-]{1,20}', value['symbol']):
        raise ValueError('Choose a valid account and ticker.')
    for key in ['settlement_date', 'buyback_expiry', 'sale_expiry']:
        try:
            value[key] = date.fromisoformat(value[key]).isoformat()
        except (ValueError, TypeError):
            raise ValueError('Enter valid settlement and expiry dates.') from None
    if value['settlement_date'] > date.today().isoformat() or any(value['settlement_date'] > value[key] for key in ['buyback_expiry', 'sale_expiry']):
        raise ValueError('Settlement must not be in the future or after either call expires.')
    if type(value['contracts']) is not int or value['contracts'] <= 0:
        raise ValueError('Enter a positive whole number of contracts for both legs.')
    if (value['buyback_expiry'], value['buyback_strike']) == (value['sale_expiry'], value['sale_strike']):
        raise ValueError('Choose a replacement call with a different strike or expiry.')
    for key in ['buyback_strike', 'sale_strike', 'buyback_price_usd', 'sale_price_usd', 'fees_usd']:
        x = value[key]
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 or (key != 'fees_usd' and x == 0):
            raise ValueError('Enter positive strikes and premiums; fees can be zero.')
    try:
        value['buyback_total_usd'] = round(value['contracts'] * 100 * value['buyback_price_usd'], 2)
        value['sale_total_usd'] = round(value['contracts'] * 100 * value['sale_price_usd'], 2)
        value['net_cash_usd'] = round(value['sale_total_usd'] - value['buyback_total_usd'] - value['fees_usd'], 2)
    except OverflowError:
        raise ValueError('Rollover amounts are too large.') from None
    if not all(math.isfinite(value[k]) for k in ['buyback_total_usd', 'sale_total_usd', 'net_cash_usd']):
        raise ValueError('Rollover amounts are too large.')
    value['created_at'] = datetime.now(timezone.utc).isoformat()
    return value


def save(data, path=DB):
    value=validate(data)
    with connect(path) as db:
        db.execute(SCHEMA['option_rollovers'])
        try:
            columns = list(value)
            record_id = db.insert_id('INSERT INTO option_rollovers (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', [value[k] for k in columns])
        except INTEGRITY_ERRORS:
            raise ValueError('This rollover is already recorded.') from None
        return dict(db.execute('SELECT * FROM option_rollovers WHERE id=?', (record_id,)).fetchone())
