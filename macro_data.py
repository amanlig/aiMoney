"""Capture public Yahoo USD/CAD reference data for the dashboard."""
from datetime import datetime, timezone
import math
import json
from urllib.request import Request, urlopen

URL = 'https://query1.finance.yahoo.com/v8/finance/chart/CAD%3DX?range=1mo&interval=1d'


def fetch(url):
    request = Request(url, headers={'User-Agent': 'CoveredCallSimulator/1.0', 'Accept': 'application/json'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def usd_cad():
    result = fetch(URL)['chart']['result'][0]
    meta = result['meta']
    rate = float(meta['regularMarketPrice'])
    if meta['symbol'] != 'CAD=X' or meta['currency'] != 'CAD' or not math.isfinite(rate) or rate <= 0:
        raise ValueError('Invalid Yahoo USD/CAD quote')
    observed = datetime.fromtimestamp(meta['regularMarketTime'], timezone.utc)
    previous = meta.get('chartPreviousClose', meta.get('previousClose'))
    previous = float(previous) if previous is not None else None
    if previous is not None and (not math.isfinite(previous) or previous <= 0):
        previous = None
    history = []
    closes = result.get('indicators', {}).get('quote', [{}])[0].get('close', [])
    for epoch, close in zip(result.get('timestamp', []), closes):
        if isinstance(close, (int, float)) and not isinstance(close, bool) and math.isfinite(close) and close > 0:
            history.append({'observed_at': datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
                            'cad_per_usd': close})
    return {'symbol': 'CAD=X', 'cad_per_usd': rate, 'previous_close': previous,
            'history': history,
            'observed_at': observed.isoformat(),
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'source': 'Yahoo Finance',
            'source_url': 'https://finance.yahoo.com/quote/CAD%3DX/', 'api_url': URL}
