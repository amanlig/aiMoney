"""Select dated USD/CAD market references without inventing broker spreads."""
from datetime import datetime, timedelta, timezone
from simulator import number

def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('FX timestamp requires a UTC offset')
    return result.astimezone(timezone.utc)


def select_latest(candidates, now=None):
    now = now or datetime.now(timezone.utc)
    valid, rejected = [], []
    for candidate in candidates:
        try:
            observed = timestamp(candidate['observed_at'])
            if observed > now + timedelta(minutes=5):
                raise ValueError('Future source timestamp')
            rate = number(candidate['cad_per_usd'], 'FX rate')
            if rate <= 0:
                raise ValueError('Nonpositive FX rate')
            if 'bid_cad_per_usd' in candidate or 'ask_cad_per_usd' in candidate:
                bid = number(candidate['bid_cad_per_usd'], 'FX bid')
                ask = number(candidate['ask_cad_per_usd'], 'FX ask')
                if bid <= 0 or ask < bid:
                    raise ValueError('Invalid FX bid/ask')
            valid.append((observed, candidate))
        except (ValueError, KeyError, TypeError, OverflowError):
            rejected.append({'source': candidate.get('source', 'Unknown'), 'reason': 'Invalid rate, timestamp or bid/ask'})
    if not valid:
        raise ValueError('No valid timestamped FX source available')
    selected = max(valid, key=lambda row: row[0])[1]
    return selected, {'selection': 'Latest valid source observation, not retrieval time',
                      'selected_source': selected['source'], 'selected_observed_at': selected['observed_at'],
                      'selected': selected, 'candidates': [c for _, c in valid], 'rejected': rejected,
                      'selected_age_seconds': (now - timestamp(selected['observed_at'])).total_seconds()}
