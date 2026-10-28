"""Generate entirely synthetic inputs; no network, brokerage or portfolio reads."""
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('exit_model', ROOT / 'model.py')
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def sample():
    today = date(2026, 10, 28)
    rng = random.Random(17)
    dates = [today - timedelta(days=i) for i in range(90, 0, -1)
             if (today - timedelta(days=i)).weekday() < 5]
    price = 47.0
    history = []
    for day in dates:
        price *= model.math.exp(rng.choice([-.035, -.018, -.008, .004, .012, .022, .04]))
        history.append(dict(date=day.isoformat(), close=round(price, 6)))

    def quote(strike, expiry, iv=.65, delay=0):
        mid = model.call_price(50, strike, (date.fromisoformat(expiry)-today).days/365, iv)
        return dict(strike=strike, expiry=expiry,
                    bidPrice=round(max(.01, mid-.10), 4), askPrice=round(mid+.10, 4),
                    bidSize=20, askSize=20, delay=delay, isHalted=False, validated=True)

    return dict(
        sample_notice='Entirely fictional inputs; no real ticker, trades, quotes or account data.',
        symbol='DEMO', account='SYNTHETIC', as_of=today.isoformat(),
        captured_at='2026-10-28T16:00:00+00:00',
        initial_purchase_price_usd=30, shares=100, contracts=1,
        stock=dict(bidPrice=49.95, askPrice=50.05, delay=0, isHalted=False),
        held=quote(40, '2027-01-15'), history=history,
        candidates=[quote(52, '2026-11-20'), quote(55, '2026-12-18'),
                    quote(60, '2027-03-19'), quote(49, '2026-12-18'),
                    quote(55, '2027-01-15', delay=15)],
        opening_reference=dict(stock_total_usd=3000, stock_cost_usd=3005,
            stock_fees_usd=5, historical_option_net_usd=700,
            prior_realized_option_usd=100, active_realized_option_usd=200,
            history_status='complete'))


if __name__ == '__main__':
    (Path(__file__).parent/'sample_input.json').write_text(json.dumps(sample(), indent=2)+'\n')
    print('Wrote synthetic sample_input.json')
