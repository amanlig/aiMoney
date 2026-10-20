"""Private covered-call exit arithmetic using explicit, user-supplied prices.

No broker connection, live pricing, forecasting or order submission.
Money values in input are decimal strings. All prices in a position share one currency.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


def number(value, label, *, nonnegative=True):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label}: expected a decimal number") from None
    if not result.is_finite() or (nonnegative and result < 0):
        raise ValueError(f"{label}: expected a finite {'nonnegative ' if nonnegative else ''}number")
    return result


def count(value, label):
    result = number(value, label)
    if result != result.to_integral_value():
        raise ValueError(f"{label}: expected a whole number")
    return int(result)


def money(value):
    return format(value.quantize(Decimal('0.01')), 'f')


def evaluate_position(position, override=None):
    """Close the entire stock position and all listed calls at explicit prices.

    Cost basis is total stock acquisition cost including acquisition fees.
    Premium is total net call cash received, after opening fees, for these calls.
    Historical realized trades, dividends and taxes are outside this position P/L.
    """
    override = override or {}
    unknown_fields = set(override) - {'stock_bid', 'call_ask', 'closing_fees', 'fx_to_cad'}
    if unknown_fields:
        raise ValueError(f'Unknown scenario fields: {sorted(unknown_fields)}')
    shares = count(position['shares'], 'shares')
    contracts = count(position.get('call_contracts', 0), 'call_contracts')
    multiplier = count(position.get('contract_multiplier', 100), 'contract_multiplier')
    if contracts == 0:
        raise ValueError(f"{position['symbol']}: a covered-call position requires short calls")
    if multiplier == 0:
        raise ValueError('contract_multiplier must be positive')
    if contracts * multiplier > shares:
        raise ValueError(f"{position['symbol']}: calls exceed stock coverage")
    stock_bid = number(override.get('stock_bid', position['stock_bid']), 'stock_bid')
    call_ask = number(override.get('call_ask', position.get('call_ask', 0)), 'call_ask')
    fees = number(override.get('closing_fees', position.get('closing_fees', 0)), 'closing_fees')
    fx = number(override.get('fx_to_cad', position['fx_to_cad']), 'fx_to_cad')
    if fx == 0:
        raise ValueError('fx_to_cad must be positive')
    if position['currency'] == 'CAD' and fx != 1:
        raise ValueError('CAD prices require fx_to_cad = 1')
    gross = shares * stock_bid
    buyback = contracts * multiplier * call_ask
    proceeds = gross - buyback - fees
    basis = position.get('stock_cost_total')
    premium = position.get('call_premium_net_total') if contracts else 0
    known = basis is not None and premium is not None
    net_invested = (number(basis, 'stock_cost_total') -
                    number(premium, 'call_premium_net_total')) if known else None
    pnl = proceeds - net_invested if known else None
    # Stock bid required to break even, holding the supplied call ask/fees fixed.
    # This is arithmetic, NOT a prediction: option prices change as stocks move.
    breakeven = (net_invested + buyback + fees) / shares if known and shares else None
    return {
        'symbol': position['symbol'], 'currency': position['currency'],
        'shares': shares, 'call_contracts': contracts,
        'call_strike_native_currency': position.get('call_strike_native_currency'),
        'call_expiry': position.get('call_expiry'),
        'stock_bid': str(stock_bid), 'call_ask': str(call_ask),
        'stock_sale': money(gross), 'call_buyback': money(buyback),
        'closing_fees': money(fees), 'net_exit_proceeds': money(proceeds),
        'net_exit_proceeds_cad': money(proceeds * fx),
        'position_pnl': money(pnl) if pnl is not None else None,
        'position_pnl_cad_equivalent': money(pnl * fx) if pnl is not None else None,
        'fixed_call_ask_breakeven_stock_bid': str(breakeven) if breakeven is not None else None,
        'cost_basis_complete': known,
        'cost_basis_context': position.get('cost_basis_context', 'User-supplied acquisition cost and net premium'),
        'execution_note': position.get('execution_note'),
    }


def evaluate_portfolio(document, scenario=None):
    scenario = scenario or {'name': 'Base supplied prices', 'overrides': {}}
    supplied_positions = document['positions']
    positions = [p for p in supplied_positions if count(p.get('call_contracts', 0), 'call_contracts') > 0]
    excluded = [p['symbol'] for p in supplied_positions if count(p.get('call_contracts', 0), 'call_contracts') == 0]
    if not positions:
        raise ValueError('No covered-call positions supplied')
    symbols = [position['symbol'] for position in positions]
    if len(set(symbols)) != len(symbols):
        raise ValueError('Duplicate symbols: combine positions or use unique position identifiers')
    overrides = scenario.get('overrides', {})
    unknown = set(overrides) - set(symbols)
    if unknown:
        raise ValueError(f'Unknown scenario symbols: {sorted(unknown)}')
    rows = [evaluate_position(position, overrides.get(position['symbol'])) for position in positions]
    # Aggregate unrounded arithmetic to avoid accumulating per-row rounding errors.
    proceeds = Decimal(0)
    pnl = Decimal(0)
    complete = True
    for position in positions:
        override = overrides.get(position['symbol'], {})
        shares = count(position['shares'], 'shares')
        contracts = count(position.get('call_contracts', 0), 'call_contracts')
        multiplier = count(position.get('contract_multiplier', 100), 'contract_multiplier')
        stock = number(override.get('stock_bid', position['stock_bid']), 'stock_bid')
        call = number(override.get('call_ask', position.get('call_ask', 0)), 'call_ask')
        fee = number(override.get('closing_fees', position.get('closing_fees', 0)), 'closing_fees')
        fx = number(override.get('fx_to_cad', position['fx_to_cad']), 'fx_to_cad')
        net = shares * stock - contracts * multiplier * call - fee
        proceeds += net * fx
        basis = position.get('stock_cost_total')
        premium = position.get('call_premium_net_total') if contracts else 0
        if basis is None or premium is None:
            complete = False
        else:
            pnl += (net - number(basis, 'stock_cost_total') + number(premium, 'call_premium_net_total')) * fx
    cash = number(document.get('cash_cad', 0), 'cash_cad', nonnegative=False)
    conversion_fees = number(scenario.get('conversion_fees_cad', document.get('conversion_fees_cad', 0)), 'conversion_fees_cad')
    resulting_cash = cash + proceeds - conversion_fees
    displayed = document.get('displayed_account_total_cad') if not excluded else None
    target = document.get('minimum_cash_target_cad')
    return {
        'scenario': scenario.get('name', 'Unnamed'),
        'scope': 'Covered-call positions only',
        'excluded_stock_only_symbols': excluded,
        'account_label': document.get('account_label', 'Unassigned'),
        'account_type': document.get('account_type', 'UNCONFIRMED'),
        'cash_status': document.get('cash_status', 'User-supplied balance'),
        'quote_context': ('Questrade captured stock bids and call asks; check source delay flags and sizes. Capture time is not a bid/ask timestamp.'
                          if scenario.get('quotes') is not None else document.get('quote_context', 'User-supplied assumptions; not live quotes')),
        'captured_at_utc': scenario.get('captured_at_utc'),
        'usd_to_cad_assumption': scenario.get('usd_to_cad_assumption'),
        'fx_metadata': scenario.get('fx_metadata'),
        'fx_settlement': scenario.get('fx_settlement'),
        'source_quotes': scenario.get('quotes'),
        'cost_basis_context': document.get('cost_basis_context', 'User-supplied costs; confirm against transaction history'),
        'positions': rows,
        'net_exit_proceeds_cad': money(proceeds),
        'existing_cash_cad': money(cash),
        'conversion_fees_cad': money(conversion_fees),
        'resulting_cash_cad': money(resulting_cash),
        'all_cost_bases_complete': complete,
        'position_pnl_cad_equivalent_before_tax': money(pnl - conversion_fees) if complete else None,
        'unreconciled_account_difference_cad': money(number(displayed, 'displayed_account_total_cad', nonnegative=False) - resulting_cash) if displayed is not None else None,
        'minimum_cash_target_cad': money(number(target, 'minimum_cash_target_cad')) if target is not None else None,
        'meets_cash_target_under_assumptions': resulting_cash >= number(target, 'minimum_cash_target_cad') if target is not None else None,
        'limitations': [
            'Totals cover stock positions with short calls only. Existing cash is separate; stock-only holdings are excluded.',
            'Supplied prices are assumptions; fills and liquidity are not simulated.',
            'Account discrepancy is not realized loss. Existing cash already includes historical cash flows.',
            'P/L uses supplied position costs and premiums; excludes taxes, dividends and earlier realized trades.',
            'Foreign-currency P/L translated at exit FX is not historical CAD tax-basis P/L.',
            'No assignment, adjusted deliverables, margin funding or settlement model; confirm with broker.',
            'Resulting cash remains inside the indicated account; withdrawals are not modeled.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('portfolio', type=Path)
    parser.add_argument('--scenarios', type=Path, help='JSON array of explicit price/FX/fee scenarios')
    parser.add_argument('--output', type=Path, help='Save JSON results locally')
    args = parser.parse_args()
    try:
        document = json.loads(args.portfolio.read_text())
        scenarios = json.loads(args.scenarios.read_text()) if args.scenarios else [None]
        results = [evaluate_portfolio(document, scenario) for scenario in scenarios]
        output = json.dumps(results, indent=2)
        if args.output:
            args.output.write_text(output + '\n')
        print(output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'Input error: {error}\n')


if __name__ == '__main__':
    main()
