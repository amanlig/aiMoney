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
    matches = [p for p in optimizer.holdings() if p['account'] == request.get('account') and p['symbol'] == request.get('symbol')]
    if len(matches) != 1:
        raise ValueError('Choose a saved covered-call holding.')
    h = matches[0]
    path = optimizer.ROOT/'reports'/f"exit-optimizer-{h['account'].lower()}-{h['symbol'].lower()}.json"
    if not path.exists():
        raise ValueError('Refresh data & analyze first.')
    original = json.loads(path.read_text())['inputs']
    if request.get('captured_at') != original['captured_at']:
        raise ValueError('Quotes changed. Reload the analysis before requesting a recommendation.')
    inputs = optimizer.model.stock_price_scenario(original, request.get('stock_price'))
    baseline = optimizer.model.evaluate(original)
    analysis = optimizer.model.evaluate(inputs)
    modes = request.get('modes', {})
    if not isinstance(modes, dict) or len(modes) > 100 or any(v not in ('close', 'expire') for v in modes.values()):
        raise ValueError('Invalid rollover exit choices.')
    rolls = []
    for row in analysis['top_choices'][:3]:
        key = f"{h['account']}|{h['symbol']}|{row['expiry']}|{row['strike']:g}"
        rolls.append(row['expire_worthless'] if modes.get(key) == 'expire' else row)
    return dict(created_at=datetime.now(timezone.utc).isoformat(), currency='USD', fees=0,
                goal=GOALS[request['goal']], captured_at=original['captured_at'],
                position={k:original[k] for k in ('account','symbol','shares','contracts','held')},
                opening_reference=original.get('opening_reference'), sources=original.get('sources'),
                captured_stock=original['stock'], hypothetical_stock_price=request['stock_price'],
                close_today=next(r for r in baseline['rows'] if r['strategy']=='Close now'),
                displayed_rollovers=rolls, assumptions=analysis['assumptions'],
                model_version=analysis['version'], search=analysis['search'],
                sale_floor_usd=analysis['minimum_stock_sale_price_usd'],
                limitations=['No live news, macro health, account cash balance or broker margin calculation.',
                             'Close today is fixed at captured quotes; rollovers use the selected slider scenario.',
                             'Expire is conditional on worthless expiry; retained stock value is excluded from option-only P&L.'])


def generate(request):
    return service.generate(snapshot(request))
