"""Local OCR and database dataset for reviewed FX transactions."""
from database_schema import SCHEMA
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
from database import connect as database_connect, INTEGRITY_ERRORS
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data/fx-samples.sqlite3'


def connect(path=DB):
    db = database_connect(path)
    db.execute(SCHEMA['samples'])
    return db


def records(path=DB):
    with connect(path) as db:
        return [dict(row) for row in db.execute('SELECT * FROM samples ORDER BY settlement_date DESC, id DESC')]


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Expected transaction fields.')
    result = {}
    for field, choices in {'account': ['TFSA','RRSP','Other CAD'], 'instrument': ['stock','option'],
                           'action': ['buy','sell'], 'direction': ['buy_usd','sell_usd']}.items():
        if data.get(field) not in choices:
            raise ValueError(f'Choose {field}.')
        result[field] = data[field]
    result['symbol'] = str(data.get('symbol', '')).strip().upper()
    if not re.fullmatch(r'[A-Z0-9.\-]{1,20}', result['symbol']):
        raise ValueError('Enter a stock symbol.')
    for field in ['trade_date', 'settlement_date']:
        value = data.get(field)
        result[field] = date.fromisoformat(value).isoformat() if value else None
    if not result['settlement_date'] or result['settlement_date'] > date.today().isoformat():
        raise ValueError('Enter a settlement date that is not in the future.')
    if result['trade_date'] and result['trade_date'] > result['settlement_date']:
        raise ValueError('Trade date must not follow settlement date.')
    for field in ['usd_amount', 'cad_amount', 'applied_rate', 'commission_usd']:
        value = data.get(field)
        if field == 'commission_usd' and value is None:
            result[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (field != 'commission_usd' and value == 0):
            raise ValueError(f'Enter a valid {field}.')
        result[field] = value
    if abs(result['cad_amount'] - result['usd_amount'] * result['applied_rate']) > max(.10, result['usd_amount'] * .000051):
        raise ValueError('CAD total does not reconcile with USD converted × applied rate. Check OCR and commissions.')
    if data.get('reviewed') is not True:
        raise ValueError('Review the extracted fields and confirm before saving.')
    result['notes'] = str(data.get('notes', ''))[:1000]
    return result


def yahoo_close(day):
    start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/CAD%3DX?period1={start}&period2={start+86400}&interval=1d'
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)['chart']['result'][0]
    for stamp, close in zip(result['timestamp'], result['indicators']['quote'][0]['close']):
        if datetime.fromtimestamp(stamp, timezone.utc).date().isoformat() == day and close and math.isfinite(close):
            return close
    raise ValueError('No same-day Yahoo observation')


def save(data, path=DB, lookup=yahoo_close):
    value = validate(data)
    # Dates, direction and totals distinguish transactions; notes do not change identity.
    identity = {k: v for k, v in value.items() if k != 'notes'}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    with connect(path) as db:
        if db.execute('SELECT id FROM samples WHERE fingerprint=?', (fingerprint,)).fetchone():
            raise ValueError('This transaction is already saved.')
    try:
        value['yahoo_close'] = lookup(value['settlement_date'])
        value['yahoo_status'] = 'Settlement-day daily close; retrospective feature, unavailable before that close'
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        value['yahoo_close'] = None
        value['yahoo_status'] = 'Unavailable; sample saved without Yahoo feature'
    value.update(created_at=datetime.now(timezone.utc).isoformat(), fingerprint=fingerprint)
    with connect(path) as db:
        columns = list(value)
        try:
            record_id = db.insert_id(f'INSERT INTO samples ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', [value[k] for k in columns])
        except INTEGRITY_ERRORS:
            raise ValueError('This transaction is already saved.') from None
        return dict(db.execute('SELECT * FROM samples WHERE id=?', (record_id,)).fetchone())


def extract_fields(text, *, default_stock=True):
    values = {}
    def amount(label):
        match = re.search(label + r'\s*[:$]?\s*([\d,]+\.\d{2,8})', text, re.I)
        return float(match[1].replace(',', '')) if match else None
    values['usd_amount'] = amount(r'\bSUB\s*T[O0]TAL\b')
    values['commission_usd'] = amount(r'\bCOMMISSION\b')
    values['cad_amount'] = amount(r'\bNET\s+AM[O0]UNT\b')
    values['applied_rate'] = amount(r'CONVERTED\s+AT') or amount(r'EXCHANGE\s+RATE')
    # OCR can drop punctuation, abbreviate months, or wrap the date label.
    for field, label in [('settlement_date', r'Settlement'), ('trade_date', r'Trade')]:
        match = re.search(
            rf'\b{label}\s+Date\b\s*[:.\-]?\s*'
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}|'
            r'[A-Za-z]{3,9}\.?\s+\d{1,2}(?:\s*,\s*|\s+)\d{4}|'
            r'\d{1,2}[\s-]+[A-Za-z]{3,9}\.?[\s,-]+\d{4})\b',
            text, re.I)
        if not match:
            continue
        raw = re.sub(r'\.', '', match[1]).replace(',', ' ')
        raw = ' '.join(raw.split())
        for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%B %d %Y', '%b %d %Y',
                    '%d %B %Y', '%d %b %Y', '%d-%B-%Y', '%d-%b-%Y'):
            try:
                values[field] = datetime.strptime(raw, fmt).date().isoformat()
                break
            except ValueError:
                continue
    if re.search(r'\bBOUGHT\b', text, re.I):
        values.update(action='buy', direction='buy_usd')
    elif re.search(r'\bSOLD\b', text, re.I):
        values.update(action='sell', direction='sell_usd')
    # Tesseract often reads CALL as CaII or CA11 in small contract text.
    option_label = r'\b(?:CA[L1I]{2}|PUT)\b'
    match = re.search(option_label + r'\s+([A-Z][A-Z0-9.\-]{0,19})\b', text, re.I)
    if match:
        values.update(symbol=match[1].upper(), instrument='option')
    elif re.search(option_label + r'|\b(?:OPEN|CLOSING)\s+CONTRACT\b', text, re.I):
        values['instrument'] = 'option'
    elif re.search(r'\bC[O0]MM[O0]N[\s|:.-]+ST[O0]CK\b', text, re.I):
        values['instrument'] = 'stock'
    if default_stock:
        values.setdefault('instrument', 'stock')
    return {k: v for k, v in values.items() if v is not None}


def ocr(image):
    if not (image.startswith(b'\x89PNG\r\n\x1a\n') or image.startswith(b'\xff\xd8\xff')):
        raise ValueError('Use a PNG or JPEG image.')
    local = ROOT / '.tools/ocr/usr'
    executable = shutil.which('tesseract') or str(local / 'bin/tesseract')
    env = dict(os.environ)
    if local.exists():
        env['LD_LIBRARY_PATH'] = str(local / 'lib/x86_64-linux-gnu')
        env['TESSDATA_PREFIX'] = str(local / 'share/tesseract-ocr/5/tessdata')
    # Temporary image is removed even on OCR failure; it is never written to the database.
    with tempfile.TemporaryDirectory(prefix='investment-ocr-') as directory:
        source = Path(directory) / 'confirmation'
        source.write_bytes(image)
        texts = []
        fields = {}
        # Single-block OCR can lose totals in widely spaced confirmation tables.
        # Column-aware segmentation provides a second reading when fields are missing.
        expected = {'usd_amount', 'cad_amount', 'applied_rate', 'settlement_date',
                    'instrument', 'action', 'direction'}
        def reconciles(candidate):
            if not {'usd_amount', 'cad_amount', 'applied_rate'} <= candidate.keys():
                return False
            difference = abs(candidate['cad_amount'] - candidate['usd_amount'] * candidate['applied_rate'])
            return difference <= max(.10, candidate['usd_amount'] * .000051)

        for mode in ('6', '4'):
            result = subprocess.run([executable, str(source), 'stdout', '-l', 'eng', '--psm', mode],
                                    env=env, capture_output=True, timeout=45, check=True)
            text = result.stdout.decode('utf-8', errors='replace')
            texts.append(text)
            reading = extract_fields(text, default_stock=False)
            candidate = {**fields, **reading}
            if reconciles(candidate):
                fields = candidate
            else:
                for key, value in reading.items():
                    fields.setdefault(key, value)
            ticker_found = fields.get('instrument') != 'option' or 'symbol' in fields
            if expected <= fields.keys() and ticker_found and reconciles(fields):
                break
        # Do not prefill a subtotal that contradicts the conversion totals.
        if {'usd_amount', 'cad_amount', 'applied_rate'} <= fields.keys() and not reconciles(fields):
            fields.pop('usd_amount')
    fields.setdefault('instrument', 'stock')
    return {'fields': fields, 'text': '\n\n--- Additional OCR reading ---\n\n'.join(texts)}
