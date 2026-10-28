"""Completed full-position exits, with immutable execution and accounting snapshots."""
from datetime import date, datetime, timezone
import hashlib
from contextlib import nullcontext
import json
import math
from database import DB, connect, INTEGRITY_ERRORS
from database_schema import SCHEMA


def position_key(holding):
    if holding.get('position_id'):
        return holding['position_id']
    identity = [holding['account'], holding['symbol'], float(holding['shares']), int(holding['call_contracts']),
                holding['call_expiry'], float(holding['call_strike_native_currency'])]
    return hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()


def decode(row):
    record = dict(row)
    record['position'] = json.loads(record.pop('position_json'))
    record['accounting'] = json.loads(record.pop('accounting_json'))
    return record


def records(path=DB):
    with connect(path) as db:
        db.execute(SCHEMA['closed_holdings'])
        return [decode(r) for r in db.execute('SELECT * FROM closed_holdings ORDER BY close_date DESC,id DESC')]


def save(data, holding, reference, path=DB, transaction=None):
    if transaction is None and holding.get('position_id'):
        import covered_positions
        with covered_positions.transaction(path) as db:
            current=covered_positions.holding(covered_positions.get(db,holding['position_id'],active=False))
            return save(data,current,reference,path,transaction=db)
    if not isinstance(data, dict) or data.get('reviewed') is not True:
        raise ValueError('Verify the stock sale and call buyback against your confirmation.')
    key = position_key(holding)
    if holding.get('position_revision') and data.get('position_revision') != holding['position_revision']:
        raise ValueError('The position changed. Reopen Close and verify the current position.')
    if data.get('position_key') != key or data.get('account') != holding['account'] or data.get('symbol') != holding['symbol']:
        raise ValueError('The holding changed. Reopen Close and verify the current position.')
    try:
        close_date = date.fromisoformat(data.get('close_date')).isoformat()
    except (ValueError, TypeError):
        raise ValueError('Enter a valid close date.') from None
    if close_date > date.today().isoformat():
        raise ValueError('Close date cannot be in the future.')
    if reference.get('last_option_transaction_date', reference.get('option_settlement_date')) and close_date < reference.get('last_option_transaction_date', reference.get('option_settlement_date')):
        raise ValueError('Close date cannot precede the latest recorded opening or rollover.')
    for field in ['stock_price_usd', 'buyback_price_usd', 'fees_usd']:
        value = data.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (field == 'stock_price_usd' and value == 0):
            raise ValueError('Enter a positive stock sale price, a nonnegative buyback price, and fees (0 for none).')
    shares, contracts = holding['shares'], holding['call_contracts']
    if shares <= 0 or contracts <= 0 or shares < contracts * 100:
        raise ValueError('Choose a valid fully covered position to close.')
    try:
        sale = round(shares * data['stock_price_usd'], 2)
        buyback = round(contracts * 100 * data['buyback_price_usd'], 2)
        cash = round(sale - buyback - data['fees_usd'], 2)
        net, cost = reference.get('historical_option_net_usd'), reference.get('stock_cost_usd')
        finite = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
        realized = round(cash + net - cost, 2) if finite(net) and finite(cost) else None
    except OverflowError:
        raise ValueError('Closing amounts are too large.') from None
    if not all(math.isfinite(x) for x in [sale, buyback, cash]) or (realized is not None and not math.isfinite(realized)):
        raise ValueError('Closing amounts are too large.')
    record = dict(position_key=key, account=holding['account'], symbol=holding['symbol'], close_date=close_date,
                  shares=shares, contracts=contracts, expiry=holding['call_expiry'], strike=float(holding['call_strike_native_currency']),
                  stock_price_usd=data['stock_price_usd'], buyback_price_usd=data['buyback_price_usd'], fees_usd=data['fees_usd'],
                  stock_sale_usd=sale, buyback_total_usd=buyback, closing_cash_usd=cash, realized_pl_usd=realized,
                  position_json=json.dumps(holding, allow_nan=False), accounting_json=json.dumps(reference, allow_nan=False),
                  created_at=datetime.now(timezone.utc).isoformat())
    with (nullcontext(transaction) if transaction is not None else connect(path)) as db:
        db.execute(SCHEMA['closed_holdings'])
        if db.table_exists('option_expirations') and db.execute('SELECT id FROM option_expirations WHERE id=?',(key,)).fetchone():
            raise ValueError('This option expired worthless; its shares remain held.')
        try:
            columns = list(record)
            record_id = db.insert_id('INSERT INTO closed_holdings (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', [record[k] for k in columns])
        except INTEGRITY_ERRORS:
            raise ValueError('This holding is already closed.') from None
        return decode(db.execute('SELECT * FROM closed_holdings WHERE id=?', (record_id,)).fetchone())
