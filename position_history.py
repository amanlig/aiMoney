"""Resolve one constant-size short-call chain without aggregating unrelated trades."""

def resolve(account, symbol, held, contracts, openings, rollovers):
    def contract(expiry, strike):
        return (expiry, float(strike))
    current = contract(held['expiry'], held['strike'])
    rolls = [r for r in rollovers if r['account'] == account and r['symbol'] == symbol]
    chain, visited = [], set()
    before = '9999-12-31'
    def unavailable(message):
        return dict(history_status='incomplete', history_note=message, historical_option_net_usd=None,
                    rollover_count=len(chain), rollover_ids=[r['id'] for r in reversed(chain)])
    while True:
        if current in visited:
            return unavailable('Rollover history revisits a contract. Resolve the trade sequence before calculating P/L.')
        visited.add(current)
        candidates = [r for r in rolls if contract(r['sale_expiry'], r['sale_strike']) == current and r['settlement_date'] <= before]
        if not candidates:
            break
        if len(candidates) != 1 or candidates[0]['contracts'] != contracts:
            return unavailable('Rollover history is ambiguous or contract counts differ. Record one complete, constant-size chain.')
        roll = candidates[0]
        chain.append(roll)
        before = roll['settlement_date']
        current = contract(roll['buyback_expiry'], roll['buyback_strike'])
    matches = [r for r in openings if r['account'] == account and r['symbol'] == symbol
               and contract(r['expiry'], r['strike']) == current and r['contracts'] == contracts
               and r['settlement_date'] <= before]
    if len(matches) != 1:
        return unavailable('Record exactly one original opening sale for the first contract in the rollover chain; missing or duplicate openings prevent cumulative P/L.')
    opening = matches[0]
    gross = opening['price_usd'] * contracts * 100
    opening_fees = opening.get('fees_usd', 0)
    sale_total = sum(r['sale_total_usd'] for r in chain)
    buyback_total = sum(r['buyback_total_usd'] for r in chain)
    fees = opening_fees + sum(r['fees_usd'] for r in chain)
    return dict(history_status='linked', history_note='P/L includes the recorded opening and linked rollovers. Unrecorded trades cannot be included.',
                historical_option_net_usd=gross + sale_total - buyback_total - fees,
                active_realized_option_usd=gross + sale_total - buyback_total - fees - (chain[0]['sale_total_usd'] if chain else gross),
                option_total_usd=gross, option_price_usd=opening['price_usd'], option_settlement_date=opening['settlement_date'],
                original_option_expiry=opening['expiry'], original_option_strike=opening['strike'],
                opening_record_id=opening['id'], last_option_transaction_date=chain[0]['settlement_date'] if chain else opening['settlement_date'], historical_option_sales_usd=gross + sale_total,
                historical_option_buybacks_usd=buyback_total, historical_option_fees_usd=fees,
                rollover_count=len(chain), rollover_ids=[r['id'] for r in reversed(chain)])
