"""Offline coverage checks and argument propagation for configurable strike rules."""
import copy
import unittest
from unittest.mock import patch
import exit_optimizer as optimizer


class CriteriaCoverage(unittest.TestCase):
    def fixture(self):
        return dict(initial_purchase_price_usd=50,stock=dict(bidPrice=39,askPrice=41),held=dict(expiry='2028-01-21'),as_of='2026-10-30',interest_rate=dict(rate=.04))

    def test_wider_range_requires_explicit_quote_refresh(self):
        data=self.fixture();before=copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError,'Refresh data & analyze'):
            optimizer.with_rollover_criteria(data,dict(purchase_price_multiplier=1))
        data['stock']=dict(bidPrice=69,askPrice=71)
        self.assertEqual(optimizer.with_rollover_criteria(data,dict(purchase_price_multiplier=1))['rollover_criteria']['purchase_price_multiplier'],1)
        self.assertEqual(before['stock'],dict(bidPrice=39,askPrice=41))
        data['candidate_coverage']=dict(minimum_strike=30,maximum_strike=100)
        with self.assertRaisesRegex(ValueError,'Refresh data & analyze'):
            optimizer.with_rollover_criteria(data,dict(purchase_price_multiplier=1))
        bounded=optimizer.with_rollover_criteria(data,dict(purchase_price_multiplier=1,max_strike_above_midpoint_pct=10))
        self.assertEqual(bounded['rollover_criteria']['max_strike_above_midpoint_pct'],10)

    def test_scenario_passes_all_criteria_explicitly(self):
        data=self.fixture();data['candidate_coverage']=dict(minimum_strike=0,maximum_strike=None)
        criteria=dict(purchase_price_multiplier=1.1,min_strike_above_midpoint_pct=0,max_strike_above_midpoint_pct=20)
        req=dict(account='RRSP',symbol='TEST',stock_price=40,rollover_criteria=criteria)
        with patch.object(optimizer,'select_holding'),patch.object(optimizer,'load_capture',return_value=dict(inputs=data)),patch.object(optimizer.model,'stock_price_scenario',side_effect=lambda data,price,**kwargs:data),patch.object(optimizer.model,'evaluate',return_value={}) as evaluate:
            result=optimizer.scenario(req)
            self.assertTrue(evaluate.call_args.kwargs['close_at_mid'])
            for key,value in criteria.items():self.assertEqual(evaluate.call_args.kwargs[key],value)
            self.assertEqual(result['inputs']['rollover_criteria'],criteria)
        self.assertNotIn('rollover_criteria',data)
