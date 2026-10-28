"""Stable covered-call positions and their exclusively owned transaction histories."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import hashlib
import math
import uuid
from zoneinfo import ZoneInfo
from database import DB, connect
from database_schema import SCHEMA
import closed_holdings
import option_rollovers
import position_history


def initialize(db):
    for name in ['covered_positions', 'covered_position_rollovers', 'closed_holdings', 'option_expirations', 'position_share_sources','deleted_position_sources','deleted_share_sources']:
        db.execute(SCHEMA[name])


@contextmanager
def transaction(path=DB):
    with connect(path) as db:
        if db.postgres:
            db.execute('SELECT pg_advisory_xact_lock(72498129)')
        else:
            db.execute('BEGIN IMMEDIATE')
        initialize(db)
        yield db


def holding(row):
    result=json.loads(row['base_json'])
    result.update(account=row['account'],symbol=row['symbol'],shares=row['shares'],
                  call_contracts=row['contracts'],call_expiry=row['expiry'],call_strike_native_currency=row['strike'],
                  position_id=row['id'],position_key=row['id'],legacy_position=row['source_key'] is not None)
    result['can_mark_expired']=row['contracts']>0 and row['expiry'] < datetime.now(ZoneInfo('America/Vancouver')).date().isoformat()
    result.setdefault('contract_multiplier',100)
    result['position_revision']=hashlib.sha256(json.dumps([row['id'],row['shares'],row['contracts'],row['expiry'],row['strike']]).encode()).hexdigest()
    return result


def rows(db):
    return list(db.execute('SELECT * FROM covered_positions ORDER BY created_at,id'))


def is_closed(db, position_id):
    return bool(db.execute('SELECT id FROM closed_holdings WHERE position_key=?',(position_id,)).fetchone())


def is_expired(db,position_id):
    return bool(db.execute('SELECT id FROM option_expirations WHERE id=?',(position_id,)).fetchone())


def is_inactive(db,position_id):
    return is_closed(db,position_id) or is_expired(db,position_id)


def get(db, position_id, active=True):
    row=db.execute('SELECT * FROM covered_positions WHERE id=?',(position_id,)).fetchone()
    if row is None or (active and is_inactive(db,position_id)):
        raise ValueError('Choose an active position.')
    return row


def legacy_records(db, table):
    return [dict(r) for r in db.execute('SELECT * FROM '+table)] if db.table_exists(table) else []


def synchronize(raw, path=DB):
    """Import each account/ticker once. Never rewrite existing positions from stale files."""
    with transaction(path) as db:
        groups={}
        for item in raw: groups.setdefault((item['account'],item['symbol']),[]).append(item)
        for (account,symbol),items in groups.items():
            if db.execute('SELECT id FROM covered_positions WHERE account=? AND symbol=?',(account,symbol)).fetchone(): continue
            for item in items:
                key=closed_holdings.position_key(item)
                if db.execute('SELECT source_key FROM deleted_position_sources WHERE source_key=?',(key,)).fetchone(): continue
                db.execute('INSERT INTO covered_positions(id,account,symbol,shares,contracts,expiry,strike,source_key,base_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (key,account,symbol,item['shares'],item['call_contracts'],item['call_expiry'],float(item['call_strike_native_currency']),key,json.dumps(item),datetime.now(timezone.utc).isoformat()))
        # Claim legacy records only if an entire uniquely resolved chain is unowned.
        openings=[]
        for table,kind in [('option_premiums','cad'),('option_premium_sales_usd','usd')]:
            openings += [dict(r,_source=kind+':'+str(r['id'])) for r in legacy_records(db,table)]
        rolls=legacy_records(db,'option_rollovers')
        for row in rows(db):
            if row['opening_json'] is not None or row['source_key'] is None: continue
            if db.execute('SELECT id FROM covered_position_rollovers WHERE position_id=?',(row['id'],)).fetchone(): continue
            h=holding(row)
            ref=position_history.resolve(row['account'],row['symbol'],dict(expiry=row['expiry'],strike=row['strike']),row['contracts'],openings,rolls)
            if ref.get('history_status')!='linked':
                if not ref.get('rollover_ids') or not ref.get('history_note','').startswith('Record exactly one'): continue
                selected=[r for r in rolls if r['id'] in ref['rollover_ids']]
                try: expected=opening_contract(row,selected)
                except ValueError: continue
                if any(r['account']==row['account'] and r['symbol']==row['symbol'] and r['contracts']==row['contracts'] and (r['expiry'],float(r['strike']))==expected for r in openings): continue
                if any(db.execute('SELECT id FROM covered_position_rollovers WHERE source_key=?',('legacy:'+str(r['id']),)).fetchone() for r in selected): continue
                for record in selected:
                    key='legacy:'+str(record['id'])
                    db.execute('INSERT INTO covered_position_rollovers(id,position_id,source_key,record_json) VALUES (?,?,?,?)',(key,row['id'],key,json.dumps(record)))
                continue
            matched=[r for r in openings if r['account']==row['account'] and r['symbol']==row['symbol'] and r['id']==ref['opening_record_id']
                     and r['expiry']==ref['original_option_expiry'] and float(r['strike'])==float(ref['original_option_strike'])]
            if len(matched)!=1: continue
            opening=matched[0]
            if db.execute('SELECT id FROM covered_positions WHERE opening_source=?',(opening['_source'],)).fetchone(): continue
            if any(db.execute('SELECT id FROM covered_position_rollovers WHERE source_key=?',('legacy:'+str(i),)).fetchone() for i in ref['rollover_ids']): continue
            db.execute('UPDATE covered_positions SET opening_json=?,opening_source=? WHERE id=?',(json.dumps(opening),opening['_source'],row['id']))
            for record in rolls:
                if record['id'] in ref['rollover_ids']:
                    key='legacy:'+str(record['id'])
                    db.execute('INSERT INTO covered_position_rollovers(id,position_id,source_key,record_json) VALUES (?,?,?,?)',
                               (key,row['id'],key,json.dumps(record)))
        for row in rows(db):
            if db.execute('SELECT id FROM position_share_sources WHERE id=?',(row['id'],)).fetchone() is None:
                assign_share_sources(db,row,row['shares'],row['created_at'],inherit=row['source_key'] is None)
        return [dict(holding(r),option_expired=is_expired(db,r['id'])) for r in rows(db)]


def history(position_id, path=DB, db=None):
    if db is None:
        with transaction(path) as current: return history(position_id,path,current)
    row=get(db,position_id,active=False)
    opening=json.loads(row['opening_json']) if row['opening_json'] else None
    rolls=[json.loads(r['record_json']) for r in db.execute('SELECT record_json FROM covered_position_rollovers WHERE position_id=?',(position_id,))]
    rolls.sort(key=lambda r:(r['settlement_date'],r.get('history_sequence',0),r.get('created_at',''),str(r['id'])))
    return dict(position=holding(row),opening=opening,rollovers=rolls,status='expired_worthless' if is_expired(db,position_id) else 'closed' if is_closed(db,position_id) else 'active')


def retain_stock_holdings(raw=(),path=DB,db=None):
    """Expose unconsumed retained shares as stock-only holdings, including older expiries."""
    if db is None:
        with transaction(path) as current:return retain_stock_holdings(raw,path,current)
    pools={};bases={};allocated={};used={};saved_rows={r['id']:r for r in rows(db)}
    deleted={r['source_key'] for r in db.execute('SELECT source_key FROM deleted_position_sources')}
    for item in raw:
        if closed_holdings.position_key(item) in deleted:continue
        pair=(item['account'],item['symbol']);pools[pair]=pools.get(pair,0)+item['shares']
    if db.table_exists('stock_cost_basis'):
        for basis in db.execute("SELECT * FROM stock_cost_basis ORDER BY CASE WHEN currency='USD' THEN 0 ELSE 1 END"):
            pair=(basis['account'],basis['symbol'])
            if pair not in bases:bases[pair]=basis;pools[pair]=basis['quantity']
    for row in saved_rows.values():
        if not is_expired(db,row['id']):
            pair=(row['account'],row['symbol']);allocated[pair]=allocated.get(pair,0)+row['shares']
    for source in db.execute('SELECT links_json FROM position_share_sources UNION ALL SELECT links_json FROM deleted_share_sources'):
        for link in json.loads(source['links_json']):used[link['position_id']]=used.get(link['position_id'],0)+link['shares']
    already_retained={json.loads(row['base_json']).get('retained_from_position_id') for row in saved_rows.values()}
    created=[]
    for receipt in db.execute('SELECT id,account,symbol,shares_retained FROM option_expirations ORDER BY created_at,id').fetchall():
        if receipt['id'] in already_retained or is_closed(db,receipt['id']):continue
        pair=(receipt['account'],receipt['symbol']);occupied=allocated.get(pair,0)
        total=pools.get(pair,max(receipt['shares_retained'],occupied))
        quantity=min(max(0,total-occupied),max(0,receipt['shares_retained']-used.get(receipt['id'],0)))
        if quantity<=0:continue
        source=saved_rows[receipt['id']]
        base=json.loads(source['base_json'])
        for key in ['historical_expiration_for','retained_from_position_id','position_id','position_key','position_revision','legacy_position','option_expired','can_mark_expired']:
            base.pop(key,None)
        own=base.get('stock_purchase');basis=bases.get(pair)
        if own:
            base['stock_purchase']=dict(own,quantity=quantity,feesUsd=(own.get('feesUsd') or 0)*quantity/own['quantity'])
        elif basis is not None and basis['price_usd'] is not None:
            base['stock_purchase']=dict(date=basis['purchase_date'],quantity=quantity,priceUsd=basis['price_usd'],feesUsd=(basis['fees_usd'] or 0)*quantity/basis['quantity'])
        base['retained_from_position_id']=receipt['id']
        position_id=uuid.uuid4().hex
        db.execute("INSERT INTO covered_positions(id,account,symbol,shares,contracts,expiry,strike,base_json,created_at) VALUES (?,?,?,?,0,'',0,?,?)",
                   (position_id,receipt['account'],receipt['symbol'],quantity,json.dumps(base),datetime.now(timezone.utc).isoformat()))
        db.execute('INSERT INTO position_share_sources(id,links_json) VALUES (?,?)',(position_id,json.dumps([dict(position_id=receipt['id'],shares=quantity)])))
        allocated[pair]=occupied+quantity;used[receipt['id']]=used.get(receipt['id'],0)+quantity
        created.append(holding(get(db,position_id)))
    return created


def capacity(db, inventory, account, symbol, excluding=None):
    total=inventory.get((account,symbol),0)
    if db.table_exists('stock_cost_basis'):
        bases=list(db.execute('SELECT quantity,currency FROM stock_cost_basis WHERE account=? AND symbol=? ORDER BY currency DESC',(account,symbol)))
        if bases: total=bases[0]['quantity']
    allocated=sum(r['shares'] for r in rows(db) if r['account']==account and r['symbol']==symbol and r['id']!=excluding and not is_expired(db,r['id']))
    return total,allocated


def availability(inventory,path=DB):
    with transaction(path) as db:
        pairs=set(inventory)
        if db.table_exists('stock_cost_basis'):
            pairs.update((r['account'],r['symbol']) for r in db.execute('SELECT account,symbol FROM stock_cost_basis'))
        result=[]
        for account,symbol in sorted(pairs):
            total,allocated=capacity(db,inventory,account,symbol)
            result.append(dict(account=account,symbol=symbol,total_shares=total,allocated_shares=allocated,available_shares=max(0,total-allocated)))
        return result


def create(data,inventory,template=None,path=DB):
    account=data.get('account');symbol=str(data.get('symbol','')).strip().upper()
    if (account,symbol) not in inventory:
        # An explicitly saved stock purchase can establish a new stock pool.
        with transaction(path) as db:
            if not db.table_exists('stock_cost_basis') or not db.execute('SELECT id FROM stock_cost_basis WHERE account=? AND symbol=?',(account,symbol)).fetchone():
                raise ValueError('Record the stock purchase before allocating a position.')
    contracts=data.get('contracts'); shares=data.get('shares');strike=data.get('strike')
    if type(contracts) is not int or contracts<=0: raise ValueError('Enter a positive whole number of contracts.')
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in [shares,strike]) or shares<contracts*100:
        raise ValueError('Allocate at least 100 shares for each call contract and enter a positive strike.')
    try: expiry=date.fromisoformat(data.get('expiry')).isoformat()
    except (ValueError,TypeError): raise ValueError('Enter a valid call expiry.') from None
    if expiry<date.today().isoformat(): raise ValueError('A new active call position must not be expired.')
    with transaction(path) as db:
        total,allocated=capacity(db,inventory,account,symbol)
        if allocated+shares>total: raise ValueError(f'Not enough unallocated shares: {max(0,total-allocated):g} available.')
        if any(r['account']==account and r['symbol']==symbol and r['expiry']==expiry and r['strike']==strike and not is_inactive(db,r['id']) for r in rows(db)):
            raise ValueError('This call contract already has an active position. Edit that position instead.')
        position_id=uuid.uuid4().hex
        base={k:v for k,v in (template or {}).items() if k not in {'position_id','position_key','position_revision','legacy_position','option_expired','can_mark_expired','historical_expiration_for','retained_from_position_id','stock_purchase'}}
        base.update(account=account,symbol=symbol)
        db.execute('INSERT INTO covered_positions(id,account,symbol,shares,contracts,expiry,strike,base_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                   (position_id,account,symbol,shares,contracts,expiry,strike,json.dumps(base),datetime.now(timezone.utc).isoformat()))
        current=get(db,position_id)
        assign_share_sources(db,current,shares,current['created_at'])
        return holding(current)


def allocate(position_id,shares,inventory,path=DB):
    with transaction(path) as db:
        row=get(db,position_id)
        if isinstance(shares,bool) or not isinstance(shares,(int,float)) or not math.isfinite(shares) or shares<row['contracts']*100:
            raise ValueError('Keep at least 100 allocated shares for each existing call.')
        total,other=capacity(db,inventory,row['account'],row['symbol'],position_id)
        if shares+other>total: raise ValueError('This allocation exceeds the recorded share pool.')
        resize_share_sources(db,row,shares)
        db.execute('UPDATE covered_positions SET shares=? WHERE id=?',(shares,position_id))
        return holding(get(db,position_id))


def opening_contract(row,rolls):
    current=(row['expiry'],float(row['strike'])); seen=set()
    while True:
        if current in seen: raise ValueError('Resolve the repeated-contract history before entering an opening.')
        seen.add(current)
        matches=[r for r in rolls if (r['sale_expiry'],float(r['sale_strike']))==current]
        if not matches: return current
        if len(matches)!=1: raise ValueError('The rollover history is ambiguous.')
        current=(matches[0]['buyback_expiry'],float(matches[0]['buyback_strike']))


def save_opening(position_id,data,edit=False,path=DB):
    if data.get('reviewed') is not True: raise ValueError('Verify the opening sale against your confirmation.')
    with transaction(path) as db:
        row=get(db,position_id); existing=json.loads(row['opening_json']) if row['opening_json'] else None
        if bool(existing)!=edit:
            raise ValueError('This position already has its one opening sale. Use Edit.' if existing else 'No opening sale exists to edit.')
        try:
            expiry=date.fromisoformat(data.get('expiry')).isoformat();settlement=date.fromisoformat(data.get('settlement_date')).isoformat()
        except (ValueError,TypeError): raise ValueError('Enter valid expiry and settlement dates.') from None
        price=data.get('price_usd');strike=data.get('strike');contracts=data.get('contracts')
        starting_call=row['contracts']==0 and existing is None
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in [price,strike]) or type(contracts) is not int or contracts<=0 or (not starting_call and contracts!=row['contracts']) or contracts*100>row['shares']:
            raise ValueError('Enter a positive premium and strike for this position’s contract count.')
        if settlement>date.today().isoformat() or settlement>expiry: raise ValueError('Check the opening settlement date.')
        saved=history(position_id,path,db)['rollovers']
        expected=(existing['expiry'],existing['strike']) if existing else opening_contract(row,saved)
        if saved and settlement>min(r['settlement_date'] for r in saved):
            raise ValueError('The original opening must precede its rollovers.')
        differs=(expiry,float(strike))!=(expected[0],float(expected[1]))
        historical=differs and not starting_call and not existing and not saved and (data.get('historical_opening') is True or data.get('expired_worthless') is True)
        if differs and not historical and not starting_call:
            raise ValueError('For an earlier original call, check the original-before-rollovers box. Otherwise use a separate position or a rollover.' if not existing and not saved else 'The opening contract must match the start of this position’s recorded rollover history.')
        if historical and settlement>row['expiry']:
            raise ValueError('The original opening must precede the current call’s expiry.')
        if not historical:
            for link in share_sources(db,position_id):
                parent=get(db,link['position_id'],active=False)
                if (starting_call or json.loads(parent['base_json']).get('historical_expiration_for')==position_id) and settlement<parent['expiry']:
                    raise ValueError('The current opening sale must follow the recorded original call’s expiry.')
        record=dict(existing or {},id=position_id,position_id=position_id,account=row['account'],symbol=row['symbol'],expiry=expiry,strike=strike,
                    contracts=contracts,settlement_date=settlement,price_usd=price,gross_usd=round(price*contracts*100,2),created_at=(existing or {}).get('created_at',datetime.now(timezone.utc).isoformat()))
        if historical: record['historical_opening']=True
        if not math.isfinite(record['gross_usd']): raise ValueError('Opening premium is too large.')
        if 'fx' in record:
            record['net_usd']=record['gross_usd']-record.get('fees_usd',0)
            record['net_cad']=round(record['net_usd']*record['fx'],2)
        if data.get('expired_worthless') is True:
            return archive_original_expiry(db,row,record,data.get('expiration_fees_usd',0),saved)
        if starting_call:
            purchase=json.loads(row['base_json']).get('stock_purchase',{})
            if purchase.get('date') and settlement<purchase['date']: raise ValueError('The option sale must follow the stock purchase.')
            db.execute('UPDATE covered_positions SET contracts=?,expiry=?,strike=? WHERE id=?',(contracts,expiry,strike,position_id))
        db.execute('UPDATE covered_positions SET opening_json=? WHERE id=?',(json.dumps(record,allow_nan=False),position_id))
        return record


def archive_original_expiry(db,row,opening,fees,rollovers):
    """Record an earlier completed cycle without ending the currently held call."""
    if isinstance(fees,bool) or not isinstance(fees,(int,float)) or not math.isfinite(fees) or fees<0:
        raise ValueError('Enter nonnegative expiration fees in USD (0 for none).')
    if opening['expiry']>=datetime.now(ZoneInfo('America/Vancouver')).date().isoformat():
        raise ValueError('Record worthless expiry after the expiry date, once your broker confirms no assignment.')
    if row['contracts']>0 and (opening['expiry'],opening['strike'])==(row['expiry'],row['strike']):
        raise ValueError('Use Expired worthless to finish the current call. This checkbox is for an earlier original call.')
    if (row['contracts']>0 and opening['expiry']>=row['expiry']) or rollovers:
        raise ValueError('This must be an earlier expired call with no recorded buybacks. Resolve its rollover history first.')
    for other in rows(db):
        base=json.loads(other['base_json'])
        if base.get('historical_expiration_for')!=row['id'] or not other['opening_json']: continue
        saved=json.loads(other['opening_json'])
        if (saved['expiry'],saved['strike'],saved['settlement_date'])==(opening['expiry'],opening['strike'],opening['settlement_date']):
            raise ValueError('This original call’s worthless expiry is already recorded.')
    previous=share_sources(db,row['id'])
    for link in previous:
        parent=db.execute('SELECT expiry FROM option_expirations WHERE id=?',(link['position_id'],)).fetchone()
        if parent is None or parent['expiry']>opening['settlement_date']:
            raise ValueError('This original sale overlaps already-linked option history. Resolve that history before recording its expiry.')
    archived_id=uuid.uuid4().hex
    archived_opening=dict(opening,id=archived_id,position_id=archived_id)
    archived_opening.pop('historical_opening',None)
    base=json.loads(row['base_json']);base['historical_expiration_for']=row['id']
    # Preserve the original source's child ordering when inserting an earlier cycle.
    db.execute('UPDATE covered_positions SET opening_json=NULL,opening_source=NULL WHERE id=?',(row['id'],))
    db.execute('INSERT INTO covered_positions(id,account,symbol,shares,contracts,expiry,strike,opening_json,opening_source,base_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
               (archived_id,row['account'],row['symbol'],row['shares'],opening['contracts'],opening['expiry'],opening['strike'],
                json.dumps(archived_opening,allow_nan=False),row['opening_source'],json.dumps(base),row['created_at']))
    db.execute('INSERT INTO position_share_sources(id,links_json) VALUES (?,?)',(archived_id,json.dumps(previous)))
    archived=get(db,archived_id)
    preview=expiration_preview(archived_id,db=db)
    receipt=record_expiration(db,archived,preview,fees)
    db.execute('INSERT INTO position_share_sources(id,links_json) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET links_json=excluded.links_json',
               (row['id'],json.dumps([dict(position_id=archived_id,shares=row['shares'])])))
    return dict(opening,expired_worthless=True,expiration_id=archived_id,realized_option_pl_usd=receipt['realized_option_pl_usd'])


def save_rollover(position_id,data,path=DB):
    with transaction(path) as db:
        row=get(db,position_id)
        if row['contracts']==0: raise ValueError('Record an option opening sale before a rollover.')
        record=option_rollovers.validate(dict(data,account=row['account'],symbol=row['symbol']))
        saved=history(position_id,path,db)
        if not saved['opening']: raise ValueError('Record this position’s opening sale before its rollovers.')
        expected=(row['expiry'],row['strike'])
        if saved['opening'].get('historical_opening'):
            previous=saved['rollovers'][-1] if saved['rollovers'] else None
            expected=(previous['sale_expiry'],previous['sale_strike']) if previous else (saved['opening']['expiry'],saved['opening']['strike'])
        if record['contracts']!=row['contracts'] or (record['buyback_expiry'],record['buyback_strike'])!=expected:
            raise ValueError('The buyback must match the last recorded call and this position’s contract count.')
        backfilling=expected!=(row['expiry'],row['strike'])
        latest=saved['rollovers'][-1]['settlement_date'] if saved['rollovers'] else saved['opening']['settlement_date']
        if record['settlement_date']<latest: raise ValueError('Enter rollovers in trade order after the opening sale.')
        if any(r['id']!=position_id and r['account']==row['account'] and r['symbol']==row['symbol'] and r['expiry']==record['sale_expiry'] and r['strike']==record['sale_strike'] and not is_inactive(db,r['id']) for r in rows(db)):
            raise ValueError('The replacement contract belongs to another active position.')
        record.update(id=uuid.uuid4().hex,position_id=position_id,history_sequence=max((r.get('history_sequence',0) for r in saved['rollovers']),default=0)+1)
        db.execute('INSERT INTO covered_position_rollovers(id,position_id,record_json) VALUES (?,?,?)',(record['id'],position_id,json.dumps(record)))
        if not backfilling:
            db.execute('UPDATE covered_positions SET expiry=?,strike=? WHERE id=?',(record['sale_expiry'],record['sale_strike'],position_id))
        return record


def expiration_preview(position_id,path=DB,db=None,today=None):
    if db is None:
        with transaction(path) as current: return expiration_preview(position_id,path,current,today)
    row=get(db,position_id)
    saved=history(position_id,path,db)
    reference=position_history.resolve(row['account'],row['symbol'],dict(expiry=row['expiry'],strike=row['strike']),row['contracts'],[saved['opening']] if saved['opening'] else [],saved['rollovers'])
    day=today or datetime.now(ZoneInfo('America/Vancouver')).date()
    return dict(position=holding(row),accounting=reference,can_mark_expired=row['expiry']<day.isoformat(),
                historical_option_net_usd=reference.get('historical_option_net_usd'))


def expire_worthless(position_id,data,path=DB,today=None,retain_stock=False,raw=()):
    if not isinstance(data,dict) or data.get('reviewed') is not True:
        raise ValueError('Confirm the call expired worthless without assignment and the shares are retained.')
    fees=data.get('fees_usd')
    if isinstance(fees,bool) or not isinstance(fees,(int,float)) or not math.isfinite(fees) or fees<0:
        raise ValueError('Enter nonnegative expiration fees in USD (0 for none).')
    with transaction(path) as db:
        row=get(db,position_id,active=False)
        if is_expired(db,position_id): raise ValueError('This call is already marked expired worthless.')
        if is_closed(db,position_id): raise ValueError('This position has already been closed.')
        current=holding(row)
        if data.get('position_revision')!=current['position_revision']:
            raise ValueError('The position changed. Reopen Expired worthless and verify the current call.')
        preview=expiration_preview(position_id,path,db,today)
        if not preview['can_mark_expired']:
            raise ValueError('Record worthless expiry after the expiry date, once your broker confirms no assignment.')
        receipt=record_expiration(db,row,preview,fees)
        if retain_stock:
            retained=retain_stock_holdings(raw,path,db)
            receipt['retained_position']=next((h for h in retained if h.get('retained_from_position_id')==position_id),None)
        return receipt


def record_expiration(db,row,preview,fees):
    net=preview['historical_option_net_usd']
    realized=round(net-fees,2) if net is not None else None
    if realized is not None and not math.isfinite(realized): raise ValueError('Expiration amounts are too large.')
    record=dict(id=row['id'],account=row['account'],symbol=row['symbol'],expiry=row['expiry'],strike=row['strike'],
                contracts=row['contracts'],shares_retained=row['shares'],fees_usd=fees,cash_flow_usd=-fees if fees else 0,
                realized_option_pl_usd=realized,position_json=json.dumps(holding(row)),accounting_json=json.dumps(preview['accounting']),
                created_at=datetime.now(timezone.utc).isoformat())
    columns=list(record)
    db.execute('INSERT INTO option_expirations ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',[record[k] for k in columns])
    return decode_expiration(record)


def decode_expiration(row):
    record=dict(row);record['position_id']=record['id'];record['event']='expired_worthless'
    record['position']=json.loads(record.pop('position_json'));record['accounting']=json.loads(record.pop('accounting_json'))
    record.update(stock_sale_usd=0,buyback_total_usd=0)
    return record


def expirations(path=DB):
    with transaction(path) as db:
        return [decode_expiration(r) for r in db.execute('SELECT * FROM option_expirations ORDER BY expiry DESC,created_at DESC,id')]


def share_sources(db,position_id):
    row=db.execute('SELECT links_json FROM position_share_sources WHERE id=?',(position_id,)).fetchone()
    return json.loads(row['links_json']) if row else []


def assign_share_sources(db,row,additional,cutoff,inherit=True):
    """FIFO retained-share reuse; every source share may fund only one immediate child."""
    links=share_sources(db,row['id'])
    if inherit and additional>0:
        used={}
        for saved in db.execute('SELECT links_json FROM position_share_sources UNION ALL SELECT links_json FROM deleted_share_sources'):
            for link in json.loads(saved['links_json']): used[link['position_id']]=used.get(link['position_id'],0)+link['shares']
        candidates=db.execute('SELECT id,shares_retained FROM option_expirations WHERE account=? AND symbol=? AND created_at<=? ORDER BY created_at,id',(row['account'],row['symbol'],cutoff))
        for source in candidates:
            if source['id']==row['id']: continue
            available=max(0,source['shares_retained']-used.get(source['id'],0))
            take=min(additional,available)
            if take<=0: continue
            found=next((link for link in links if link['position_id']==source['id']),None)
            if found: found['shares']+=take
            else: links.append(dict(position_id=source['id'],shares=take))
            additional-=take
            if additional<=0: break
    db.execute('INSERT INTO position_share_sources(id,links_json) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET links_json=excluded.links_json',(row['id'],json.dumps(links)))


def resize_share_sources(db,row,shares):
    links=share_sources(db,row['id'])
    if shares>row['shares']:
        assign_share_sources(db,row,shares-row['shares'],datetime.now(timezone.utc).isoformat())
    else:
        # Keep the oldest retained-share lots; release fresh shares first.
        remaining=shares;kept=[]
        for link in links:
            take=min(remaining,link['shares'])
            if take>0: kept.append(dict(position_id=link['position_id'],shares=take));remaining-=take
        db.execute('INSERT INTO position_share_sources(id,links_json) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET links_json=excluded.links_json',(row['id'],json.dumps(kept)))


def prior_realized(position_id,path=DB,db=None):
    if db is None:
        with transaction(path) as current: return prior_realized(position_id,path,current)
    get(db,position_id,active=False)
    incoming={};children={}
    for row in db.execute('SELECT p.id,p.created_at,s.links_json FROM covered_positions p JOIN position_share_sources s ON p.id=s.id UNION ALL SELECT id,created_at,links_json FROM deleted_share_sources ORDER BY created_at,id'):
        links=json.loads(row['links_json']);incoming[row['id']]=links
        for link in links: children.setdefault(link['position_id'],[]).append((row['id'],link['shares']))
    receipts={r['id']:dict(r) for r in db.execute('SELECT * FROM option_expirations')}
    cache={}
    def rounded(value): return int(value.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    def credits(current,seen):
        if current in seen: return {},True
        if current in cache: return cache[current]
        result={};unknown=False
        for link in incoming.get(current,[]):
            parent=receipts.get(link['position_id'])
            if parent is None or parent['shares_retained']<=0:
                unknown=True;continue
            inherited,missing=credits(parent['id'],seen|{current})
            amounts=dict(inherited);unknown=unknown or missing
            if parent['realized_option_pl_usd'] is None: unknown=True
            else: amounts[parent['id']]=rounded(Decimal(str(parent['realized_option_pl_usd']))*100)
            start=Decimal(0)
            for child,quantity in children.get(parent['id'],[]):
                if child==current: break
                start+=Decimal(str(quantity))
            end=start+Decimal(str(link['shares']));total=Decimal(str(parent['shares_retained']))
            for source,cents in amounts.items():
                allocated=rounded(Decimal(cents)*end/total)-rounded(Decimal(cents)*start/total)
                result[source]=result.get(source,0)+allocated
        cache[current]=(result,unknown)
        return result,unknown
    amounts,unknown=credits(position_id,set())
    fractions={}
    def provenance(current,weight,seen):
        if current in seen:return
        for link in incoming.get(current,[]):
            parent=receipts.get(link['position_id'])
            if parent is None or parent['shares_retained']<=0:continue
            fraction=weight*link['shares']/parent['shares_retained']
            fractions[parent['id']]=fractions.get(parent['id'],0)+fraction
            provenance(parent['id'],fraction,seen|{current})
    provenance(position_id,1,set())
    return dict(prior_realized_option_usd=None if unknown else sum(amounts.values())/100,
                realized_sources=[dict(position_id=key,fraction=value,realized_pl_usd=amounts[key]/100 if key in amounts else None) for key,value in fractions.items()],
                realized_history_note='Linked realized option history is incomplete.' if unknown else 'Realized P/L follows retained shares reused for this position; partial allocations receive proportional P/L, with cents allocated in creation order.')
