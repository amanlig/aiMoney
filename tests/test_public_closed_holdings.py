import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import closed_holdings as closed


class ClosedHoldingsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'test.sqlite3'
        self.holding = dict(account='RRSP', symbol='TEST', shares=200, call_contracts=2,
                            call_expiry='2028-01-21', call_strike_native_currency=35)
        self.body = dict(account='RRSP', symbol='TEST', position_key=closed.position_key(self.holding),
                         close_date='2026-10-27', stock_price_usd=40, buyback_price_usd=10,
                         fees_usd=20, reviewed=True)
        self.reference = dict(stock_cost_usd=4010, historical_option_net_usd=1973,
                              history_status='linked', rollover_count=2, last_option_transaction_date='2026-10-26')

    def test_actual_exit_and_realized_pl_preserve_snapshot(self):
        row = closed.save(self.body, self.holding, self.reference, self.path)
        self.assertEqual(row['stock_sale_usd'], 8000)
        self.assertEqual(row['buyback_total_usd'], 2000)
        self.assertEqual(row['closing_cash_usd'], 5980)
        self.assertEqual(row['realized_pl_usd'], 3943)
        self.reference['historical_option_net_usd'] = 999999
        saved = closed.records(self.path)[0]
        self.assertEqual(saved['accounting']['historical_option_net_usd'], 1973)
        self.assertEqual(saved['realized_pl_usd'], 3943)
        self.assertEqual(saved['position'], self.holding)

    def test_duplicate_close_is_rejected(self):
        closed.save(self.body, self.holding, self.reference, self.path)
        with self.assertRaisesRegex(ValueError, 'already closed'):
            closed.save(self.body, self.holding, self.reference, self.path)
        self.assertEqual(len(closed.records(self.path)), 1)

    def test_invalid_and_stale_submissions_do_not_close(self):
        for change in [dict(reviewed=False), dict(position_key='stale'), dict(account='TFSA'),
                       dict(stock_price_usd=0), dict(buyback_price_usd=-1), dict(fees_usd=-1),
                       dict(stock_price_usd=float('nan')), dict(close_date='2099-01-01'),
                       dict(close_date='2026-10-25'), dict(close_date=None)]:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    closed.save(dict(self.body, **change), self.holding, self.reference, self.path)
                self.assertEqual(closed.records(self.path), [])

    def test_incomplete_history_can_close_without_inventing_profit(self):
        row = closed.save(dict(self.body, buyback_price_usd=0), self.holding,
                          dict(history_status='incomplete', historical_option_net_usd=None, stock_cost_usd=4010), self.path)
        self.assertIsNone(row['realized_pl_usd'])
        self.assertEqual(row['closing_cash_usd'], 7980)

    def test_closed_position_stays_out_of_active_holdings_after_reload(self):
        import exit_optimizer as optimizer
        root = Path(self.folder.name)
        (root / 'data').mkdir()
        current = {k:v for k,v in self.holding.items() if k != 'account'}
        other = dict(current, symbol='OTHER')
        (root/'data/rrsp.json').write_text(json.dumps({'positions': [current, other]}))
        closed.save(self.body, self.holding, self.reference, self.path)
        original_records = closed.records
        with patch.object(optimizer, 'ROOT', root), patch.object(optimizer, 'INPUTS', {'RRSP': 'rrsp.json'}), patch.object(closed, 'records', side_effect=lambda: original_records(self.path)), patch('covered_positions.connect', side_effect=lambda path=None: __import__('database').connect(self.path)):
            self.assertEqual([h['symbol'] for h in optimizer.holdings()], ['OTHER'])
            self.assertEqual(len(optimizer.holdings(include_closed=True)), 2)
            self.assertEqual([h['symbol'] for h in optimizer.holdings()], ['OTHER'])
        changed = dict(self.holding, call_strike_native_currency=40)
        self.assertNotEqual(closed.position_key(changed), self.body['position_key'])
