"""Read recorded trades for one holding and its allocated expired-call history."""
from decimal import Decimal, ROUND_HALF_UP

import covered_positions as positions
import position_history
from database import DB


def amount(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def report(position_id, path=DB):
    with positions.transaction(path) as db:
        selected = positions.get(db, position_id, active=False)
        holding = positions.holding(selected)
        prior = positions.prior_realized(position_id, db=db)
        entries = []
        purchase = holding.get('stock_purchase')
        if not purchase and db.table_exists('stock_cost_basis'):
            basis = db.execute("SELECT * FROM stock_cost_basis WHERE account=? AND symbol=? AND price_usd IS NOT NULL ORDER BY CASE WHEN currency='USD' THEN 0 ELSE 1 END",
                               (selected['account'], selected['symbol'])).fetchone()
            if basis:
                purchase = dict(date=basis['purchase_date'], quantity=holding['shares'], priceUsd=basis['price_usd'],
                                feesUsd=(basis['fees_usd'] or 0)*holding['shares']/basis['quantity'])
        if purchase:
            gross = amount(holding['shares']*purchase['priceUsd'])
            fees = amount((purchase.get('feesUsd') or 0)*holding['shares']/purchase['quantity'])
            entries.append(dict(id=position_id+':stock', date=purchase['date'], action='Buy', instrument='Stock',
                                expiry=None, strike=None, quantity=holding['shares'], unit='shares', price_usd=purchase['priceUsd'],
                                gross_usd=gross, fees_usd=fees, cash_flow_usd=amount(-gross-fees),
                                outcome='Shares held', expired=None, realized_pl_usd=None))

        sources = [(source['position_id'], source['fraction'], source['realized_pl_usd']) for source in prior['realized_sources']]
        sources.append((position_id, 1, None))
        current_reference = None
        for source_id, fraction, allocated_realized in sources:
            saved = positions.history(source_id, db=db)
            row = positions.get(db, source_id, active=False)
            receipt = db.execute('SELECT * FROM option_expirations WHERE id=?', (source_id,)).fetchone()
            reference = position_history.resolve(row['account'], row['symbol'], dict(expiry=row['expiry'], strike=row['strike']),
                                                 row['contracts'], [saved['opening']] if saved['opening'] else [], saved['rollovers'])
            if source_id == position_id:
                current_reference = reference if row['contracts'] else None
            own_entries = []
            pending = None

            def event(key, day, action, expiry, strike, contracts, price, fees=0):
                gross = amount(Decimal(str(price))*contracts*100*Decimal(str(fraction)))
                fee = amount(Decimal(str(fees))*Decimal(str(fraction)))
                entry = dict(id=source_id+':'+str(key), date=day, action=action, instrument='Call', expiry=expiry, strike=strike,
                             quantity=contracts*fraction, unit='contracts', price_usd=price, gross_usd=gross, fees_usd=fee,
                             cash_flow_usd=amount((gross if action == 'Sell' else -gross)-fee), outcome='Outcome not recorded',
                             expired=False, realized_pl_usd=None)
                own_entries.append(entry)
                return entry

            if saved['opening']:
                sale = saved['opening']
                pending = event('opening', sale['settlement_date'], 'Sell', sale['expiry'], sale['strike'], sale['contracts'],
                                sale['price_usd'], sale.get('fees_usd', 0))
            for roll in saved['rollovers']:
                buy = event(str(roll['id'])+':buy', roll['settlement_date'], 'Buy', roll['buyback_expiry'], roll['buyback_strike'],
                            roll['contracts'], roll['buyback_price_usd'], roll['fees_usd'])
                buy['outcome'] = 'Bought back'
                group = source_id+':'+str(roll['id'])
                buy.update(rollover_group=group, rollover_leg='buyback')
                buy['rollover_net_cash_usd'] = amount(Decimal(str(roll['net_cash_usd']))*Decimal(str(fraction)))
                if pending and (pending['expiry'], pending['strike'], pending['quantity']) == (buy['expiry'], buy['strike'], buy['quantity']):
                    pending['outcome'] = 'Bought back'
                    buy['realized_pl_usd'] = amount(pending['gross_usd']-pending['fees_usd']-buy['gross_usd']-buy['fees_usd'])
                pending = event(str(roll['id'])+':sell', roll['settlement_date'], 'Sell', roll['sale_expiry'], roll['sale_strike'],
                                roll['contracts'], roll['sale_price_usd'])
                pending.update(rollover_group=group, rollover_leg='replacement')
            if receipt:
                fee = amount(Decimal(str(receipt['fees_usd']))*Decimal(str(fraction)))
                expiry_entry = dict(id=source_id+':expiry', date=receipt['expiry'], action='Expiry', instrument='Call',
                                    expiry=receipt['expiry'], strike=receipt['strike'], quantity=receipt['contracts']*fraction,
                                    unit='contracts', price_usd=None, gross_usd=0, fees_usd=fee, cash_flow_usd=-fee,
                                    outcome='Expired worthless', expired=True, realized_pl_usd=None)
                if pending and (pending['expiry'], pending['strike']) == (receipt['expiry'], receipt['strike']):
                    pending.update(outcome='Expired worthless', expired=True)
                    expiry_entry['realized_pl_usd'] = amount(pending['gross_usd']-pending['fees_usd']-fee)
                    # Preserve the exact cents already allocated to these retained shares.
                    known = [e['realized_pl_usd'] for e in own_entries if e['action'] == 'Buy']
                    target = allocated_realized if source_id != position_id else receipt['realized_option_pl_usd']
                    if target is not None and all(value is not None for value in known):
                        expiry_entry['realized_pl_usd'] = amount(target-sum(known))
                    # One readable row for a sale that subsequently expired worthless.
                    pending.update(realized_pl_usd=expiry_entry['realized_pl_usd'],
                                   fees_usd=amount(pending['fees_usd']+fee),
                                   cash_flow_usd=amount(pending['cash_flow_usd']-fee),
                                   expired_on=receipt['expiry'])
                else:
                    own_entries.append(expiry_entry)
            elif pending and (pending['expiry'], pending['strike'], pending['quantity']) == (row['expiry'], row['strike'], row['contracts']*fraction):
                pending['outcome'] = 'Open'
            entries.extend(own_entries)

        # Dates are settlement dates for trades and contract dates for confirmed expiry.
        entries.sort(key=lambda entry: entry['date'] or '9999-12-31')
        for entry in entries:
            entry['signed_gross_usd'] = -entry['gross_usd'] if entry['action'] == 'Buy' else entry['gross_usd']
        gross_cash = amount(sum(Decimal(str(e['signed_gross_usd'])) for e in entries))
        closing = [e for e in entries if e['instrument'] == 'Call' and (e['action'] in ['Buy', 'Expiry'] or e['expired'])]
        complete = (current_reference is None or current_reference['history_status'] == 'linked') and prior['prior_realized_option_usd'] is not None
        complete = complete and all(e['realized_pl_usd'] is not None for e in closing)
        realized = amount(sum(e['realized_pl_usd'] for e in closing)) if complete else None
        option_cash = amount(sum(e['cash_flow_usd'] for e in entries if e['instrument'] == 'Call'))
        open_premium = amount(sum(e['gross_usd']-e['fees_usd'] for e in entries if e['action'] == 'Sell' and e['outcome'] == 'Open'))
        groups = {}
        for entry in entries:
            if entry.get('rollover_group'):
                groups.setdefault(entry['rollover_group'], {})[entry['rollover_leg']] = entry
        cash_entries = []
        seen = set()
        for entry in entries:
            group = entry.get('rollover_group')
            legs = groups.get(group, {})
            if set(legs) == {'buyback', 'replacement'}:
                if group in seen:
                    continue
                seen.add(group)
                buy, sale = legs['buyback'], legs['replacement']
                net = amount(buy['cash_flow_usd']+sale['cash_flow_usd'])
                cash_entries.append(dict(id=group, date=buy['date'], action='Rollover', instrument='Call',
                                         quantity=buy['quantity'], unit='contracts', expiry=sale['expiry'], strike=sale['strike'],
                                         price_usd=None, signed_gross_usd=amount(buy['signed_gross_usd']+sale['signed_gross_usd']),
                                         fees_usd=amount(buy['fees_usd']+sale['fees_usd']), cash_flow_usd=net, option_cash_usd=net,
                                         buyback=dict(expiry=buy['expiry'], strike=buy['strike'], price_usd=buy['price_usd'], gross_usd=buy['gross_usd']),
                                         replacement=dict(expiry=sale['expiry'], strike=sale['strike'], price_usd=sale['price_usd'], gross_usd=sale['gross_usd']),
                                         outcome=sale['outcome'], expired=sale['expired']))
            else:
                cash_entries.append(dict(entry, option_cash_usd=entry['cash_flow_usd'] if entry['instrument']=='Call' else None))
        return dict(position_id=position_id, account=holding['account'], symbol=holding['symbol'], entries=entries,
                    cash_entries=cash_entries,
                    net_rollover_cash_usd=amount(sum(e['option_cash_usd'] for e in cash_entries if e['action']=='Rollover')),
                    gross_cash_flow_usd=gross_cash,
                    realized_option_pl_usd=realized, net_option_cash_usd=option_cash, open_call_premium_usd=open_premium,
                    history_complete=complete, allocated_history=any(fraction != 1 for _, fraction, _ in sources),
                    note='Expired calls combine their sale and confirmed worthless expiry in one row, dated by the sale. Rollover net cash = replacement sale minus buyback and fees. Realized option P/L = the closed call’s original sale minus its buyback and fees. Stock gains and losses are excluded. All rollover fees are charged on the buyback row. Open-call premiums are not realized profit.')
