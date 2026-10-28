import tempfile
from pathlib import Path
import unittest
import option_rollovers as rolls


class RolloverTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'rolls.sqlite3'
        self.data = dict(account='RRSP', symbol='RKLB', settlement_date='2026-10-26', contracts=10,
                         buyback_expiry='2028-01-21', buyback_strike=25, buyback_price_usd=30,
                         sale_expiry='2028-01-21', sale_strike=40, sale_price_usd=32,
                         fees_usd=20, reviewed=True)

    def test_both_legs_persist_once_with_correct_credit(self):
        saved = rolls.save(self.data, self.path)
        self.assertEqual(saved['buyback_total_usd'], 30000)
        self.assertEqual(saved['sale_total_usd'], 32000)
        self.assertEqual(saved['net_cash_usd'], 1980)
        self.assertEqual(rolls.records(self.path), [saved])
        with self.assertRaisesRegex(ValueError, 'already recorded'):
            rolls.save(self.data, self.path)
        self.assertEqual(len(rolls.records(self.path)), 1)

    def test_debit_and_zero_fee(self):
        saved = rolls.save(dict(self.data, sale_price_usd=25, fees_usd=0), self.path)
        self.assertEqual(saved['net_cash_usd'], -5000)

    def test_invalid_leg_does_not_save_either_leg(self):
        for patch in [dict(reviewed=False), dict(contracts=1.5), dict(contracts=True),
                      dict(buyback_price_usd=-1), dict(sale_price_usd=float('nan')),
                      dict(sale_strike=25), dict(fees_usd=-1), dict(settlement_date='2099-01-01'),
                      dict(sale_expiry='2025-01-01'), dict(buyback_expiry=None), dict(symbol='')]:
            with self.subTest(patch=patch):
                with self.assertRaises(ValueError):
                    rolls.save(dict(self.data, **patch), self.path)
                self.assertEqual(rolls.records(self.path), [])
