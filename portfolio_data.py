"""Shared saved-portfolio data shaping for Profile settings and offline reports."""
from decimal import Decimal
from simulator import evaluate_portfolio, evaluate_position

ACCOUNT_CURRENCIES = {'RRSP': 'CAD', 'TFSA': 'CAD', 'LIRA': 'USD'}

def account_widget(document, scenario=None):
    """Keep native snapshot currencies; captured scenarios use simulator CAD output."""
    covered = [p for p in document['positions'] if p.get('call_contracts', 0) > 0]
    excluded = [p['symbol'] for p in document['positions'] if not p.get('call_contracts', 0)]
    if scenario:
        if any(p['currency'] != 'CAD' for p in covered):
            raise ValueError('Captured CAD scenarios require CAD cost bases; keep this USD snapshot native until those are supplied')
        result = evaluate_portfolio(document, scenario)
        currency = 'CAD'
        positions = result['positions']
        value_key, pnl_key = 'net_exit_proceeds_cad', 'position_pnl_cad_equivalent'
        context = result['quote_context']
        captured = result['captured_at_utc']
    else:
        currencies = {p['currency'] for p in covered}
        if len(currencies) > 1:
            raise ValueError('An account with mixed currencies needs a CAD quote scenario')
        currency = next(iter(currencies), 'CAD')
        # Unit FX is used only for native arithmetic here. No CAD conversion is inferred.
        positions = [evaluate_position(dict(p, fx_to_cad='1')) for p in covered]
        value_key, pnl_key = 'net_exit_proceeds', 'position_pnl'
        context = document.get('quote_context', 'Saved supplied marks')
        captured = document.get('captured_at_utc')
    if currency != ACCOUNT_CURRENCIES.get(document['account_type'], currency):
        raise ValueError('Account input currency must match its default: LIRA USD; RRSP and TFSA CAD')
    rows = [dict(symbol=p['symbol'], net=p[value_key], pnl=p[pnl_key],
                 shares=p['shares'], contracts=p['call_contracts'],
                 strike=p['call_strike_native_currency'], expiry=p['call_expiry'])
            for p in positions]
    saved = {p['symbol']: p for p in covered}
    positions = [dict(
        symbol=p['symbol'], currency=currency, shares=p['shares'], contracts=p['call_contracts'],
        strike=float(p['call_strike_native_currency']) if p['call_strike_native_currency'] is not None else None,
        expiry=p['call_expiry'], snapshotStock=float(p['stock_bid']), snapshotCall=float(p['call_ask']),
        cost=float(saved[p['symbol']]['stock_cost_total']) if saved[p['symbol']].get('stock_cost_total') is not None else None,
        premium=float(saved[p['symbol']]['call_premium_net_total']) if saved[p['symbol']].get('call_premium_net_total') is not None else None,
        entryFx=float(saved[p['symbol']]['purchase_fx_to_cad']) if saved[p['symbol']].get('purchase_fx_to_cad') is not None else None,
        purchaseContext=saved[p['symbol']].get('purchase_context'),
        fees=float(p['closing_fees']),
        markSource='api' if scenario or document.get('position_source') == 'Questrade API' else 'snapshot') for p in positions]
    total = sum((Decimal(r['net']) for r in rows), Decimal(0))
    pnl = (sum((Decimal(r['pnl']) for r in rows), Decimal(0))
           if rows and all(r['pnl'] is not None for r in rows) else None)
    return dict(account=document['account_type'], currency=currency, rows=rows,
                net=str(total), pnl=str(pnl) if pnl is not None else None,
                context=context, captured=captured, excluded=excluded,
                positions=positions)

