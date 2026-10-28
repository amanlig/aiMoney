"""Create stock-first holdings and remove one holding's owned records."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import uuid

from database import DB
from database_schema import SCHEMA
import covered_positions as positions
import stock_basis


def purchase(data):
    quantity=data.get('shares');price=data.get('price_usd');fees=data.get('fees_usd')
    if not data.get('purchase_date') or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in [quantity,price,fees]):
        raise ValueError('Enter a purchase date, shares, USD price and fees (0 for none).')
    return stock_basis.validate(dict(account=data.get('account'),symbol=data.get('symbol'),currency='USD',date=data['purchase_date'],
                                     quantity=quantity,priceUsd=price,feesUsd=fees,fx=None,totalCost=quantity*price+fees))


def pool(db,account,symbol):
    db.execute(SCHEMA['stock_cost_basis'])
    return db.execute("SELECT * FROM stock_cost_basis WHERE account=? AND symbol=? ORDER BY CASE WHEN currency='USD' THEN 0 ELSE 1 END LIMIT 1",(account,symbol)).fetchone()


def save_pool(db,account,symbol,quantity,price,fees,day):
    if quantity<=0:
        db.execute('DELETE FROM stock_cost_basis WHERE account=? AND symbol=?',(account,symbol));return
    db.execute('''INSERT INTO stock_cost_basis(account,symbol,currency,purchase_date,quantity,price_usd,fees_usd,purchase_fx,total_cost,updated_at)
      VALUES (?,?,'USD',?,?,?,?,NULL,?,?) ON CONFLICT(account,symbol,currency) DO UPDATE SET purchase_date=excluded.purchase_date,
      quantity=excluded.quantity,price_usd=excluded.price_usd,fees_usd=excluded.fees_usd,total_cost=excluded.total_cost,updated_at=excluded.updated_at''',
      (account,symbol,day,quantity,price,max(0,fees),quantity*price+max(0,fees),datetime.now(timezone.utc).isoformat()))


def preserve_other_purchases(db,account,symbol,basis,excluding=None):
    if basis is None:return
    for row in positions.rows(db):
        if row['id']==excluding or row['account']!=account or row['symbol']!=symbol:continue
        base=json.loads(row['base_json'])
        if base.get('stock_purchase'):continue
        base['stock_purchase']=dict(date=basis['purchase_date'],quantity=row['shares'],priceUsd=basis['price_usd'],
                                    feesUsd=(basis['fees_usd'] or 0)*row['shares']/basis['quantity'])
        db.execute('UPDATE covered_positions SET base_json=? WHERE id=?',(json.dumps(base),row['id']))


def create(data,path=DB):
    value=purchase(data)
    with positions.transaction(path) as db:
        account,symbol=value['account'],value['symbol'];old=pool(db,account,symbol)
        existing=[r for r in positions.rows(db) if r['account']==account and r['symbol']==symbol]
        if old is None and existing:raise ValueError('Record the existing stock purchase before adding another holding for this stock and account.')
        if old is not None and not isinstance(old['price_usd'],(int,float)):
            raise ValueError('Record the existing USD purchase price before adding another holding for this stock and account.')
        preserve_other_purchases(db,account,symbol,old)
        old_quantity=old['quantity'] if old else 0
        quantity=old_quantity+value['quantity']
        price=((old['price_usd']*old_quantity if old else 0)+value['priceUsd']*value['quantity'])/quantity
        fees=(old['fees_usd'] or 0 if old else 0)+value['feesUsd']
        save_pool(db,account,symbol,quantity,price,fees,value['date'])
        position_id=uuid.uuid4().hex
        base=dict(account=account,symbol=symbol,contract_multiplier=100,stock_purchase={key:value[key] for key in ['date','quantity','priceUsd','feesUsd']})
        db.execute("INSERT INTO covered_positions(id,account,symbol,shares,contracts,expiry,strike,base_json,created_at) VALUES (?,?,?,?,0,'',0,?,?)",
                   (position_id,account,symbol,value['quantity'],json.dumps(base),datetime.now(timezone.utc).isoformat()))
        # A newly purchased lot does not reuse earlier retained shares.
        positions.assign_share_sources(db,positions.get(db,position_id),0,'',inherit=False)
        return positions.holding(positions.get(db,position_id))


def update_purchase(position_id,data,path=DB):
    with positions.transaction(path) as db:
        row=positions.get(db,position_id);base=json.loads(row['base_json']);previous=base.get('stock_purchase')
        if not previous:raise ValueError('Edit this imported holding’s shared stock purchase in Transactions.')
        value=purchase(dict(data,account=row['account'],symbol=row['symbol']))
        if value['quantity']<row['contracts']*100:raise ValueError('Keep at least 100 shares for each current call.')
        old=pool(db,row['account'],row['symbol'])
        quantity=old['quantity']-previous['quantity']+value['quantity']
        _,other=positions.capacity(db,{},row['account'],row['symbol'],position_id)
        if value['quantity']+other>quantity:raise ValueError('Some of these purchase shares are allocated to another holding. Adjust allocations first.')
        price=(old['price_usd']*old['quantity']-previous['priceUsd']*previous['quantity']+value['priceUsd']*value['quantity'])/quantity
        fees=(old['fees_usd'] or 0)-(previous['feesUsd'] or 0)+value['feesUsd']
        save_pool(db,row['account'],row['symbol'],quantity,price,fees,value['date'])
        positions.resize_share_sources(db,row,value['quantity'])
        base['stock_purchase']={key:value[key] for key in ['date','quantity','priceUsd','feesUsd']}
        db.execute('UPDATE covered_positions SET shares=?,base_json=? WHERE id=?',(value['quantity'],json.dumps(base),position_id))
        return positions.holding(positions.get(db,position_id))


def deletion_plan(db,position_id):
    row=positions.get(db,position_id)
    all_rows={r['id']:r for r in positions.rows(db)}
    links={key:positions.share_sources(db,key) for key in all_rows}
    reserved={}
    for marker in db.execute('SELECT links_json FROM deleted_share_sources'):
        for link in json.loads(marker['links_json']):reserved[link['position_id']]=reserved.get(link['position_id'],0)+link['shares']
    owned={position_id}
    changed=True
    while changed:
        changed=False
        for child in list(owned):
            for link in links[child]:
                parent=link['position_id']
                children={key for key,sources in links.items() if any(s['position_id']==parent for s in sources)}
                if parent in owned or parent not in all_rows or not children.issubset(owned):continue
                if sum(s['shares'] for key in children for s in links[key] if s['position_id']==parent)+reserved.get(parent,0)!=all_rows[parent]['shares']:continue
                owned.add(parent);changed=True
    if any(key not in owned and any(s['position_id'] in owned for s in sources) for key,sources in links.items()):
        raise ValueError('Another holding depends on this holding’s recorded history.')
    return row,all_rows,owned


def preview(position_id,path=DB):
    with positions.transaction(path) as db:
        row,all_rows,owned=deletion_plan(db,position_id)
        return dict(holding=positions.holding(row),position_count=len(owned),
                    opening_sales=sum(bool(all_rows[key]['opening_json']) for key in owned),
                    rollovers=sum(db.execute('SELECT COUNT(*) AS n FROM covered_position_rollovers WHERE position_id=?',(key,)).fetchone()['n'] for key in owned),
                    expired_cycles=sum(positions.is_expired(db,key) for key in owned),
                    shared_purchase=any(r['account']==row['account'] and r['symbol']==row['symbol'] and key not in owned for key,r in all_rows.items()))


def belongs(snapshot,owned,all_rows):
    position=snapshot.get('position',snapshot.get('inputs',{}))
    if not isinstance(position,dict):return False
    if position.get('position_id'):return position['position_id'] in owned
    for key in owned:
        row=all_rows[key];held=position.get('held',{})
        if row['source_key'] and (position.get('account'),position.get('symbol'),position.get('shares'),position.get('contracts'),held.get('expiry'),held.get('strike'))==(row['account'],row['symbol'],row['shares'],row['contracts'],row['expiry'],row['strike']):return True
        base=json.loads(row['base_json'])
        if row['source_key'] and (position.get('account'),position.get('symbol'),position.get('shares'),position.get('contracts'),held.get('expiry'),held.get('strike'))==(row['account'],row['symbol'],base.get('shares'),base.get('call_contracts'),base.get('call_expiry'),base.get('call_strike_native_currency')):return True
    return False


def delete(position_id,data,path=DB,reports=None):
    if data.get('confirmed') is not True:raise ValueError('Confirm deletion of this holding and its records.')
    staged=[];quarantine=None
    try:
        with positions.transaction(path) as db:
            row,all_rows,owned=deletion_plan(db,position_id)
            if data.get('position_revision')!=positions.holding(row)['position_revision']:raise ValueError('The holding changed. Reopen Delete and review it again.')
            basis=pool(db,row['account'],row['symbol'])
            preserve_other_purchases(db,row['account'],row['symbol'],basis,position_id)
            if reports is not None:
                reports=Path(reports)
                files=[]
                for file in reports.glob('exit-optimizer-*.json'):
                    if file.is_symlink():continue
                    try:matched=belongs(json.loads(file.read_text()),owned,all_rows)
                    except (ValueError,OSError):matched=any(file.name.endswith('-'+key+'.json') for key in owned)
                    if matched:files.append(file)
                if files:
                    quarantine=Path(tempfile.mkdtemp(prefix='.delete-holding-',dir=reports))
                    for file in files:
                        target=quarantine/file.name;file.rename(target);staged.append((file,target))
            if db.table_exists('recommendation_runs'):
                for run in db.execute('SELECT id,snapshot_json FROM recommendation_runs').fetchall():
                    if belongs(json.loads(run['snapshot_json']),owned,all_rows):db.execute('DELETE FROM recommendation_runs WHERE id=?',(run['id'],))
            for marker in db.execute('SELECT id,links_json FROM deleted_share_sources').fetchall():
                kept=[link for link in json.loads(marker['links_json']) if link['position_id'] not in owned]
                if kept:db.execute('UPDATE deleted_share_sources SET links_json=? WHERE id=?',(json.dumps(kept),marker['id']))
                else:db.execute('DELETE FROM deleted_share_sources WHERE id=?',(marker['id'],))
            for key in owned:
                item=all_rows[key]
                kept=[link for link in positions.share_sources(db,key) if link['position_id'] not in owned]
                if kept:db.execute('INSERT INTO deleted_share_sources(id,created_at,links_json) VALUES (?,?,?)',(key,item['created_at'],json.dumps(kept)))
                if item['source_key']:db.execute('INSERT INTO deleted_position_sources(source_key,deleted_at) VALUES (?,?) ON CONFLICT(source_key) DO NOTHING',(item['source_key'],datetime.now(timezone.utc).isoformat()))
                source=item['opening_source']
                if source:
                    kind,record_id=source.split(':',1);table={'usd':'option_premium_sales_usd','cad':'option_premiums'}[kind]
                    db.execute('DELETE FROM '+table+' WHERE id=?',(int(record_id),))
                for roll in db.execute('SELECT source_key FROM covered_position_rollovers WHERE position_id=?',(key,)):
                    if roll['source_key'] and roll['source_key'].startswith('legacy:'):db.execute('DELETE FROM option_rollovers WHERE id=?',(int(roll['source_key'].split(':')[1]),))
                db.execute('DELETE FROM closed_holdings WHERE position_key=?',(key,))
                db.execute('DELETE FROM covered_position_rollovers WHERE position_id=?',(key,))
                db.execute('DELETE FROM option_expirations WHERE id=?',(key,))
                db.execute('DELETE FROM position_share_sources WHERE id=?',(key,))
            for key in owned:db.execute('DELETE FROM covered_positions WHERE id=?',(key,))
            if basis is not None:
                remaining=max(0,basis['quantity']-row['shares'])
                own=json.loads(row['base_json']).get('stock_purchase')
                price=own['priceUsd'] if own else basis['price_usd']
                fees=(own['feesUsd'] or 0)*row['shares']/own['quantity'] if own else (basis['fees_usd'] or 0)*row['shares']/basis['quantity']
                if remaining:
                    if basis['price_usd'] is None:
                        ratio=remaining/basis['quantity']
                        db.execute('UPDATE stock_cost_basis SET quantity=quantity*?,fees_usd=fees_usd*?,total_cost=total_cost*? WHERE account=? AND symbol=?',(ratio,ratio,ratio,row['account'],row['symbol']))
                    else:
                        price=(basis['price_usd']*basis['quantity']-price*row['shares'])/remaining
                        save_pool(db,row['account'],row['symbol'],remaining,price,(basis['fees_usd'] or 0)-fees,basis['purchase_date'])
                else:save_pool(db,row['account'],row['symbol'],0,0,0,basis['purchase_date'])
    except BaseException:
        for original,target in reversed(staged):target.rename(original)
        if quarantine:quarantine.rmdir()
        raise
    for original,target in staged:target.unlink()
    if quarantine:quarantine.rmdir()
    return dict(deleted=position_id,deleted_positions=len(owned),deleted_analyses=len(staged))
