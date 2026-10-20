import json
from pathlib import Path
import unittest
from decimal import Decimal
from portfolio_data import account_widget
from questrade_quotes import call_id, ImporterError
from roll_candidates import output_path

ROOT = Path(__file__).resolve().parents[1]

class SyntheticPortfolioTests(unittest.TestCase):
    def test_native_account_values(self):
        for account, currency in [('RRSP', 'CAD'), ('TFSA', 'CAD'), ('LIRA', 'USD')]:
            with self.subTest(account=account):
                document = json.loads((ROOT/'examples'/f'{account.lower()}.json').read_text())
                result = account_widget(document)
                self.assertEqual(result['currency'], currency)
                self.assertEqual(Decimal(result['net']), Decimal('1100'))
                self.assertEqual(Decimal(result['pnl']), Decimal('300'))
                self.assertEqual(result['positions'][0]['cost'], 1000)

    def test_currency_mismatch_rejected(self):
        document = json.loads((ROOT/'examples/lira.json').read_text())
        document['positions'][0]['currency'] = 'CAD'
        with self.assertRaises(ValueError):
            account_widget(document)

    def test_exact_contract(self):
        chain = {'options': [{'expiryDate': '2030-01-18', 'chainPerRoot': [
            {'root': 'QBTS', 'multiplier': 100, 'chainPerStrikePrice': [{'strikePrice': 15, 'callSymbolId': 42}]}]}]}
        position = {'symbol': 'QBTS', 'call_expiry': '2030-01-18', 'contract_multiplier': 100, 'call_strike_native_currency': '15'}
        self.assertEqual(call_id(chain, position), 42)
        with self.assertRaises(ImporterError):
            call_id(chain, dict(position, call_strike_native_currency='16'))

    def test_capture_path_validation(self):
        with self.assertRaises(ImporterError):
            output_path('../private', 'QBTS')
