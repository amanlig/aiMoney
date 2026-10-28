import copy
import unittest
from position_history import resolve


class PositionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.opening = dict(id=1, account='RRSP', symbol='TEST', expiry='2027-01-15', strike=25,
                            contracts=2, settlement_date='2025-01-01', price_usd=8, fees_usd=5)
        self.rolls = [dict(id=1, account='RRSP', symbol='TEST', contracts=2, settlement_date='2025-02-01',
                          buyback_expiry='2027-01-15', buyback_strike=25, sale_expiry='2027-06-18', sale_strike=30,
                          buyback_total_usd=1000, sale_total_usd=1200, fees_usd=10),
                      dict(id=2, account='RRSP', symbol='TEST', contracts=2, settlement_date='2025-03-01',
                          buyback_expiry='2027-06-18', buyback_strike=30, sale_expiry='2028-01-21', sale_strike=35,
                          buyback_total_usd=900, sale_total_usd=1100, fees_usd=12)]
        self.held = dict(expiry='2028-01-21', strike=35)

    def resolve(self, openings=None, rolls=None):
        return resolve('RRSP', 'TEST', self.held, 2, openings if openings is not None else [self.opening], rolls if rolls is not None else self.rolls)

    def test_two_rolls_each_leg_and_fee_counted_once(self):
        result = self.resolve()
        self.assertEqual(result['historical_option_net_usd'], 1973)
        self.assertEqual(result['historical_option_sales_usd'], 3900)
        self.assertEqual(result['historical_option_buybacks_usd'], 1900)
        self.assertEqual(result['historical_option_fees_usd'], 27)
        self.assertEqual(result['rollover_ids'], [1, 2])
        self.assertEqual(result['option_total_usd'], 1600)
        self.assertEqual(result['active_realized_option_usd'],873)

    def test_latest_sale_duplicate_and_unrelated_trades_not_counted(self):
        latest = dict(self.opening, id=2, expiry=self.held['expiry'], strike=35, price_usd=5.5, settlement_date='2025-03-01')
        unrelated = dict(self.rolls[-1], id=3, account='TFSA')
        self.assertEqual(self.resolve([self.opening, latest], self.rolls + [unrelated])['historical_option_net_usd'], 1973)

    def test_missing_link_opening_duplicate_and_partial_roll_are_unavailable(self):
        for openings, rolls in [([], self.rolls), ([self.opening], self.rolls[1:]),
                                ([self.opening, dict(self.opening, id=9)], self.rolls),
                                ([self.opening], self.rolls + [dict(self.rolls[-1], id=9)]),
                                ([self.opening], [self.rolls[0], dict(self.rolls[1], contracts=1)])]:
            with self.subTest(openings=openings, rolls=rolls):
                result=self.resolve(openings, rolls)
                self.assertEqual(result['history_status'], 'incomplete')
                self.assertIsNone(result['historical_option_net_usd'])

    def test_direct_opening_with_no_rolls(self):
        opening=dict(self.opening, expiry=self.held['expiry'], strike=35)
        result=self.resolve([opening], [])
        self.assertEqual(result['historical_option_net_usd'], 1595)
        self.assertEqual(result['active_realized_option_usd'],-5)
        self.assertEqual(result['rollover_count'], 0)

    def test_contract_cycle_is_not_silently_aggregated(self):
        rolls=copy.deepcopy(self.rolls)
        rolls[0].update(buyback_expiry=self.held['expiry'], buyback_strike=35)
        self.assertIsNone(self.resolve(rolls=rolls)['historical_option_net_usd'])


class CaptureAccountingTests(unittest.TestCase):
    def test_recorded_original_displays_before_rollovers_connect_without_inventing_profit(self):
        from unittest.mock import patch
        import exit_optimizer as optimizer
        opening=dict(id='position-a',account='RRSP',symbol='RKLB',expiry='2025-03-21',strike=24,
                     contracts=10,settlement_date='2025-03-04',price_usd=.8,historical_opening=True)
        capture=dict(inputs=dict(account='RRSP',symbol='RKLB',position_id='position-a',shares=1000,contracts=10,
                                 held=dict(expiry='2028-01-21',strike=25)),
                     result=dict(rows=[dict(strategy='Close now',mean=25000)]))
        with patch.object(optimizer.covered_positions,'history',return_value=dict(opening=opening,rollovers=[])), \
             patch.object(optimizer.covered_positions,'prior_realized',return_value=dict(prior_realized_option_usd=0)), \
             patch.object(optimizer.stock_basis,'get',return_value=dict(priceUsd=21.4581,feesUsd=0,quantity=1000)), \
             patch.object(optimizer,'authorize') as broker:
            result=optimizer.reaccount_capture(capture)
            reference=result['inputs']['opening_reference']
            self.assertEqual(reference['option_total_usd'],800)
            self.assertEqual(reference['option_price_usd'],.8)
            self.assertEqual(reference['option_settlement_date'],'2025-03-04')
            self.assertEqual(reference['original_option_expiry'],'2025-03-21')
            self.assertEqual(reference['original_option_strike'],24)
            self.assertEqual(reference['history_status'],'incomplete')
            self.assertIn('original opening sale is recorded',reference['history_note'])
            self.assertIsNone(reference['historical_option_net_usd'])
            self.assertIsNone(result['result']['rows'][0]['net_profit_usd'])
            self.assertIsNone(result['result']['rows'][0]['total_pl_usd'])
            with patch.object(optimizer.covered_positions,'history',return_value=dict(opening=None,rollovers=[])):
                missing=optimizer.reaccount_capture(capture)
                self.assertIsNone(missing['inputs']['opening_reference']['option_total_usd'])
        broker.assert_not_called()
        self.assertNotIn('opening_reference',capture['inputs'])

    def test_saved_quotes_reaccount_without_market_fetch_or_snapshot_mutation(self):
        from unittest.mock import patch
        import exit_optimizer as optimizer
        capture=dict(inputs=dict(account='RRSP', symbol='TEST', shares=200, contracts=2,
                     held=dict(expiry='2028-01-21', strike=35)), result=dict(rows=[dict(strategy='Close now', mean=5000)]))
        reference=dict(stock_total_usd=4000, stock_cost_usd=4010, historical_option_net_usd=1973)
        with patch.object(optimizer, 'opening_reference', return_value=reference), patch.object(optimizer, 'authorize') as broker:
            result=optimizer.reaccount_capture(capture)
        broker.assert_not_called()
        self.assertEqual(result['result']['rows'][0]['net_profit_usd'], 2963)
        self.assertEqual(result['result']['rows'][0]['mean'], 5000)
        self.assertNotIn('opening_reference', capture['inputs'])
        self.assertNotIn('net_profit_usd', capture['result']['rows'][0])
