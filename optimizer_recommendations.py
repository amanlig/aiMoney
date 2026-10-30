"""Build an authoritative USD optimizer snapshot; no FX or OpenAI in the model."""
from datetime import datetime, timezone
import json
import exit_optimizer as optimizer
import optimizer_assessments as service

GOALS = {'keep_exposure': 'Prefer retaining stock; release cash if downside risk is unacceptable',
         'free_cash': 'Free cash for another investment', 'compare': 'Compare without a preferred outcome'}


def snapshot(request):
    if not isinstance(request, dict) or request.get('goal') not in GOALS:
        raise ValueError('Select a recommendation goal.')
    h=optimizer.select_holding(request)
    saved=optimizer.load_capture(request)
    if saved is None: raise ValueError('Refresh data & analyze this position first.')
    original=saved['inputs']
    if request.get('captured_at') != original['captured_at']:
        raise ValueError('Quotes changed. Reload the analysis before requesting a recommendation.')
    original = optimizer.with_interest_rate(original, request.get('interest_rate'))
    rate = original['interest_rate']['rate']
    if request.get('expected_rate') is not None and abs(request['expected_rate']-rate)>1e-10:
        raise ValueError('The interest rate changed since this chart was calculated. Recalculate the scenario before generating a recommendation.')
    inputs = optimizer.model.stock_price_scenario(original, request.get('stock_price'), rate=rate)
    baseline = optimizer.model.evaluate(original, rate=rate)
    analysis = optimizer.model.evaluate(inputs, rate=rate, close_at_mid=False)
    modes = request.get('modes', {})
    if not isinstance(modes, dict) or len(modes) > 100 or any(v not in ('close', 'expire') for v in modes.values()):
        raise ValueError('Invalid rollover exit choices.')
    rolls = []
    for row in analysis['top_choices'][:3]:
        key = f"{h['account']}|{h['symbol']}|"+(h.get('position_id')+'|' if h.get('position_id') else '')+f"{row['expiry']}|{row['strike']:g}"
        rolls.append(row['expire_worthless'] if modes.get(key) == 'expire' else row)
    return dict(created_at=datetime.now(timezone.utc).isoformat(), currency='USD', future_fees=0,
                goal=GOALS[request['goal']], captured_at=original['captured_at'],
                position={k:original[k] for k in ('account','symbol','shares','contracts','held','position_id') if k in original},
                opening_reference=original.get('opening_reference'), sources=original.get('sources'),
                captured_stock=original['stock'], hypothetical_stock_price=request['stock_price'],
                close_today=next(r for r in baseline['rows'] if r['strategy']=='Close now'),
                displayed_rollovers=rolls, assumptions=analysis['assumptions'],
                interest_rate=original['interest_rate'], model_version=analysis['version'], search=analysis['search'],
                sale_floor_usd=analysis['minimum_stock_sale_price_usd'],
                limitations=['No live news, macro health, account cash balance or broker margin calculation.',
                             'Close today is fixed at captured quotes; rollovers use the selected slider scenario.',
                             'Expire is conditional on worthless expiry; retained stock value is excluded from option-only P&L.'])


def generate(request):
    return service.generate(snapshot(request))
