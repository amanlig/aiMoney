"""Synthetic OCR parser and SQLite dataset checks."""
import tempfile
import unittest
from unittest.mock import patch
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fx_samples import extract_fields, save, records, validate, ocr

class FXSampleTests(unittest.TestCase):
    def sample(self):
        return dict(account='TFSA',symbol='TEST',instrument='option',action='buy',direction='buy_usd',settlement_date='2025-05-27',trade_date=None,usd_amount=1001,commission_usd=1,cad_amount=1401.4,applied_rate=1.4,notes='',reviewed=True)
    def test_parse(self):
        fields=extract_fields('Transaction Type: BOUGHT\nSettlement Date: MAY 27 2025\nCALL TEST 05/30/25 11.50\nSUBTOTAL 1,001.00\nCOMMISSION 1.00\nAS PRINCIPAL, WE CONVERTED AT 1.4000\nNET AMOUNT 1,401.40 C$')
        self.assertEqual(fields['settlement_date'],'2025-05-27')
        self.assertEqual(fields['usd_amount'],1001)
        self.assertEqual(fields['applied_rate'],1.4)
        self.assertEqual(fields['instrument'],'option')
        self.assertEqual(fields['direction'],'buy_usd')
    def test_date_formats(self):
        for value in ['Settlement Date MAY 27 2025',
                      'Settlement Date: May 27,2025',
                      'SETTLEMENT DATE: May 27, 2025',
                      'Settlement Date: Sep. 27, 2025',
                      'Settlement\nDate\n27 May 2025',
                      'Settlement Date: 27-May-2025',
                      'Settlement Date: 2025-05-27',
                      'Settlement Date: 2025/05/27']:
            with self.subTest(value=value):
                expected = '2025-09-27' if 'Sep.' in value else '2025-05-27'
                self.assertEqual(extract_fields(value)['settlement_date'], expected)
        fields = extract_fields('Trade Date: May 26, 2025\nSettlement Date: May 27, 2025')
        self.assertEqual(fields['trade_date'], '2025-05-26')
        self.assertEqual(fields['settlement_date'], '2025-05-27')
        for value in ['Settlement Date: February 30, 2025',
                      'Trade Date: May 27, 2025', 'Settlement Date: 05/06/2025']:
            self.assertNotIn('settlement_date', extract_fields(value))

    def test_cibc_sale_totals(self):
        text = ('Transaction Type: SOLD\nSettlement Date: APR 24 2025\n'
                '10 CALL MU 04/25/25 75 .83 U$\nEXCHANGE RATE 1.36600000\n'
                'GROSS AMOUNT 830.00\nSEC FEE 0.03\nCOMMISSION 19.45\n'
                'TOTAL FEES/CHARGES 19.48\nSUB TOTAL\n810.52\n'
                'EXCHANGE 296.65\nAS PRINCIPAL, WE CONVERTED AT 1.366\n'
                'NET AMOUNT 1,107.17 CR C$')
        fields = extract_fields(text)
        self.assertEqual(fields['usd_amount'], 810.52)
        self.assertEqual(fields['cad_amount'], 1107.17)
        self.assertEqual(fields['settlement_date'], '2025-04-24')
        self.assertEqual(fields['symbol'], 'MU')
        self.assertEqual(fields['direction'], 'sell_usd')

    def test_cibc_common_stock_sale(self):
        text = ('Transaction Type: SOLD\nSettlement Date: FEB 06 2025\n'
                '36 GE HEALTHCARE TECHNOLOGIES IN 87.1714 U$\n'
                'COMMON STOCK\nUNSOLICITED\nEXCHANGE RATE 1.40750000\n'
                'Confirmation Summary\nGROSS AMOUNT 3,138.17\n'
                'SEC FEE 0.09\nCOMMISSION 6.95\nTOTAL FEES/CHARGES 7.04\n'
                'SUBTOTAL 3,131.13\nEXCHANGE 1,275.94\n'
                'AS PRINCIPAL, WE CONVERTED AT 1.4075\nNET AMOUNT 4,407.07 CR C$')
        for subtotal in ['SUBTOTAL', 'SUB TOTAL', 'SUB\nTOTAL', 'SUBT0TAL']:
            with self.subTest(subtotal=subtotal):
                fields = extract_fields(text.replace('SUBTOTAL', subtotal))
                self.assertEqual(fields, dict(action='sell', direction='sell_usd',
                    instrument='stock', settlement_date='2025-02-06',
                    usd_amount=3131.13, commission_usd=6.95,
                    cad_amount=4407.07, applied_rate=1.4075))

    def test_ocr_retries_missing_totals(self):
        first = subprocess.CompletedProcess([], 0, b'Settlement Date: APR 24 2025\nEXCHANGE RATE 1.36600000', b'')
        second = subprocess.CompletedProcess([], 0, b'SUB TOTAL 810.52\nNET AMOUNT 1,107.17', b'')
        with patch('fx_samples.subprocess.run', side_effect=[first, second]) as run:
            result = ocr(b'\x89PNG\r\n\x1a\nsynthetic')
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result['fields']['usd_amount'], 810.52)
        self.assertEqual(result['fields']['settlement_date'], '2025-04-24')
        self.assertIn('SUB TOTAL', result['text'])

    def test_ocr_replaces_dropped_leading_digit(self):
        text = ('Settlement Date: FEB 06 2025\nSUBTOTAL 331.13\n'
                'NET AMOUNT 4,407.07\nEXCHANGE RATE 1.4075')
        first = subprocess.CompletedProcess([], 0, text.encode(), b'')
        second = subprocess.CompletedProcess([], 0, text.replace('331.13', '3,131.13').encode(), b'')
        with patch('fx_samples.subprocess.run', side_effect=[first, second]):
            result = ocr(b'\x89PNG\r\n\x1a\nsynthetic')
        self.assertEqual(result['fields']['usd_amount'], 3131.13)
        with patch('fx_samples.subprocess.run', side_effect=[first, first]):
            result = ocr(b'\x89PNG\r\n\x1a\nsynthetic')
        self.assertNotIn('usd_amount', result['fields'])

    def test_rocket_lab_stock_purchase(self):
        text = ('Transaction Type: BOUGHT\nSettlement Date: FEB 28 2025\n'
                '1,000 ROCKET LAB USA INC 21.4581 U$\nCOMMON STOCK\n'
                'UNSOLICITED\nEXCHANGE RATE 1.46650000\n'
                'GROSS AMOUNT 21,458.10\nCOMMISSION 6.95\n'
                'TOTAL FEES/CHARGES 6.95\nSUBTOTAL 21,465.05\n'
                'EXCHANGE 10,013.45\nAS PRINCIPAL, WE CONVERTED AT 1.4665\n'
                'NET AMOUNT 31,478.50 C$')
        for label in ['COMMON STOCK', 'COMMON\nSTOCK', 'C0MMON ST0CK']:
            with self.subTest(label=label):
                fields = extract_fields(text.replace('COMMON STOCK', label))
                self.assertEqual(fields['instrument'], 'stock')
                self.assertEqual(fields['action'], 'buy')
                self.assertEqual(fields['direction'], 'buy_usd')
                self.assertEqual(fields['usd_amount'], 21465.05)
                self.assertEqual(fields['cad_amount'], 31478.50)
                self.assertEqual(fields['settlement_date'], '2025-02-28')
                self.assertNotIn('symbol', fields)

    def test_ocr_retries_missing_security_type(self):
        text = ('Transaction Type: BOUGHT\nSettlement Date: FEB 28 2025\n'
                'SUBTOTAL 21,465.05\nNET AMOUNT 31,478.50\nEXCHANGE RATE 1.4665')
        first = subprocess.CompletedProcess([], 0, text.encode(), b'')
        second = subprocess.CompletedProcess([], 0, (text + '\nCOMMON STOCK').encode(), b'')
        with patch('fx_samples.subprocess.run', side_effect=[first, second]) as run:
            result = ocr(b'\x89PNG\r\n\x1a\nsynthetic')
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result['fields']['instrument'], 'stock')

    def test_asts_option_sale(self):
        text = ('Transaction Type: SOLD\nSettlement Date: MAR 03 2025\n'
                '5 CALL ASTS 03/14/25 30 2.05 U$\nAST SPACEMOBILE INC\n'
                'UNSOLICITED\nOPEN CONTRACT\nEXCHANGE RATE 1.42050000\n'
                'GROSS AMOUNT 1,025.00\nSEC FEE 0.03\nCOMMISSION 13.20\n'
                'TOTAL FEES/CHARGES 13.23\nSUBTOTAL 1,011.77\n'
                'EXCHANGE 425.45\nAS PRINCIPAL, WE CONVERTED AT 1.4205\n'
                'NET AMOUNT 1,437.22 CR C$')
        for label in ['CALL ASTS', 'Call asts', 'CaII ASTS', 'CA11 ASTS', 'CALL\nASTS']:
            with self.subTest(label=label):
                fields = extract_fields(text.replace('CALL ASTS', label))
                self.assertEqual(fields['instrument'], 'option')
                self.assertEqual(fields['symbol'], 'ASTS')
                self.assertEqual(fields['action'], 'sell')
                self.assertEqual(fields['settlement_date'], '2025-03-03')
                self.assertEqual(fields['usd_amount'], 1011.77)
                self.assertEqual(fields['cad_amount'], 1437.22)
        self.assertEqual(extract_fields('CALL')['instrument'], 'option')
        self.assertEqual(extract_fields('OPEN CONTRACT')['instrument'], 'option')

    def test_stock_default_without_common_stock_label(self):
        text = ('Transaction Type: BOUGHT\nSettlement Date: MAR 07 2025\n'
                '200 MICRON TECHNOLOGY INC 89.62 U$\nUNSOLICITED\n'
                'EXCHANGE RATE 1.45250000\nGROSS AMOUNT 17,924.00\n'
                'COMMISSION 6.95\nTOTAL FEES/CHARGES 6.95\n'
                'SUBTOTAL 17,930.95\nEXCHANGE 8,113.75\n'
                'AS PRINCIPAL, WE CONVERTED AT 1.4525\nNET AMOUNT 26,044.70 C$')
        fields = extract_fields(text)
        self.assertEqual(fields['instrument'], 'stock')
        self.assertEqual(fields['action'], 'buy')
        self.assertEqual(fields['usd_amount'], 17930.95)
        self.assertEqual(fields['cad_amount'], 26044.70)
        self.assertEqual(fields['settlement_date'], '2025-03-07')

    def test_validation(self):
        for changes in [dict(reviewed=False),dict(cad_amount=1500),dict(usd_amount=float('nan'))]:
            with self.assertRaises(ValueError):validate(dict(self.sample(),**changes))
        with self.assertRaises(ValueError):ocr(b'not an image')
    def test_persistence_and_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'samples.sqlite3'
            self.assertEqual(save(self.sample(),path,lookup=lambda day:1.38)['yahoo_close'],1.38)
            self.assertEqual(len(records(path)),1)
            with self.assertRaises(ValueError):save(self.sample(),path,lookup=lambda day:1.38)
            self.assertEqual(len(records(path)),1)
    def test_lookup_failure(self):
        def fail(day):raise OSError('offline')
        with tempfile.TemporaryDirectory() as directory:
            saved=save(self.sample(),Path(directory)/'samples.sqlite3',lookup=fail)
            self.assertIsNone(saved['yahoo_close'])
            self.assertIn('Unavailable',saved['yahoo_status'])
if __name__=='__main__':unittest.main()
