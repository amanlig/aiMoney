import json
import unittest
from decimal import Decimal

from chart import ROOT, account_widget


class AccountWidgetTests(unittest.TestCase):
    def test_lira_reconciles_both_legs_to_screenshot_in_usd(self):
        document = json.loads((ROOT / 'data/lira-screenshot-2026-10-13.json').read_text())
        result = account_widget(document)
        self.assertEqual(result['currency'], 'USD')
        self.assertEqual(result['excluded'], ['FUBO'])
        self.assertEqual(Decimal(result['net']), Decimal('48298'))
        self.assertEqual(Decimal(result['pnl']), Decimal('34940.03'))
        rows = {row['symbol']: row for row in result['rows']}
        self.assertEqual(Decimal(rows['NVDA']['pnl']), Decimal('17942.62'))
        self.assertEqual(Decimal(rows['QBTS']['pnl']), Decimal('16997.41'))
        self.assertEqual(rows['QBTS']['strike'], '30')

    def test_cad_scenario_does_not_mix_usd_cost_basis(self):
        document = json.loads((ROOT / 'data/lira-screenshot-2026-10-13.json').read_text())
        with self.assertRaisesRegex(ValueError, 'CAD cost bases'):
            account_widget(document, {'name': 'CAD scenario', 'overrides': {}})
