"""Small-data baseline: median proportional FX adjustment by direction."""
import math
from statistics import median

DIRECTIONS = ('buy_usd', 'sell_usd')


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def fit(rows):
    parameters = {}
    for direction in DIRECTIONS:
        subset = [r for r in rows if r['direction'] == direction]
        if len(subset) < 3:
            raise ValueError(f'Need at least three training samples for {direction}.')
        parameters[direction] = {
            'adjustment': median(r['applied_rate'] / r['yahoo_close'] - 1 for r in subset),
            'samples': len(subset),
            'usd_min': min(r['usd_amount'] for r in subset),
            'usd_max': max(r['usd_amount'] for r in subset),
        }
    return {'version': 1, 'method': 'median_proportional_adjustment_by_direction', 'parameters': parameters}


def predict(model, direction, reference_rate, usd_amount):
    if direction not in DIRECTIONS:
        raise ValueError('Direction must be buy_usd or sell_usd.')
    if not positive(reference_rate) or not positive(usd_amount):
        raise ValueError('Reference rate and USD amount must be finite and positive.')
    parameter = model['parameters'][direction]
    rate = reference_rate * (1 + parameter['adjustment'])
    return {'direction': direction, 'reference_rate': reference_rate,
            'estimated_rate': rate, 'usd_amount': usd_amount,
            'estimated_cad': round(usd_amount * rate, 2),
            'outside_training_amount_range': not parameter['usd_min'] <= usd_amount <= parameter['usd_max'],
            'reference_limitation': 'Trained using settlement-day Yahoo daily closes; accuracy with live or trade-day rates is unvalidated.'}


def split_dates(rows):
    dates = sorted({r['settlement_date'] for r in rows})
    if len(dates) < 5:
        raise ValueError('Need at least five distinct settlement dates.')
    cutoff = dates[min(len(dates)-1, max(1, int(len(dates)*.8)))]
    return ([r for r in rows if r['settlement_date'] < cutoff],
            [r for r in rows if r['settlement_date'] >= cutoff])


def metrics(model, rows):
    if not rows:
        return {'samples': 0}
    predictions = [predict(model, r['direction'], r['yahoo_close'], r['usd_amount']) for r in rows]
    return {'samples': len(rows),
            'mean_absolute_rate_error': sum(abs(p['estimated_rate']-r['applied_rate']) for p,r in zip(predictions,rows))/len(rows),
            'mean_absolute_cad_error': sum(abs(p['estimated_cad']-r['cad_amount']) for p,r in zip(predictions,rows))/len(rows),
            'mean_absolute_percentage_cad_error': 100*sum(abs(p['estimated_cad']-r['cad_amount'])/r['cad_amount'] for p,r in zip(predictions,rows))/len(rows),
            'max_absolute_cad_error': max(abs(p['estimated_cad']-r['cad_amount']) for p,r in zip(predictions,rows)),
            'reference_only_mean_absolute_cad_error': sum(abs(r['usd_amount']*r['yahoo_close']-r['cad_amount']) for r in rows)/len(rows)}
