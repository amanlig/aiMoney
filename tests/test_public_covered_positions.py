import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from database import connect
import covered_positions as positions
import closed_holdings


class CoveredPositionTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'positions.sqlite3'
        self.raw=dict(account='RRSP',symbol='RKLB',shares=2000,call_contracts=10,call_expiry='2028-01-21',call_strike_native_currency=20)
        self.pool={('RRSP','RKLB'):2000}
        self.january=positions.synchronize([self.raw],self.path)[0]
        positions.allocate(self.january['position_id'],1000,self.pool,self.path)
        self.february=positions.create(dict(account='RRSP',symbol='RKLB',shares=1000,contracts=10,strike=20,expiry='2028-02-18'),self.pool,path=self.path)

    def opening(self,h,price=3):
        return dict(expiry=h['call_expiry'],strike=h['call_strike_native_currency'],contracts=10,
                    settlement_date='2026-10-01',price_usd=price,reviewed=True)

    def test_two_contracts_have_separate_ids_and_one_opening_each(self):
        january=positions.save_opening(self.january['position_id'],self.opening(self.january),path=self.path)
        february=positions.save_opening(self.february['position_id'],self.opening(self.february,4),path=self.path)
        self.assertNotEqual(january['position_id'],february['position_id'])
        with self.assertRaisesRegex(ValueError,'one opening'):
            positions.save_opening(self.january['position_id'],dict(self.opening(self.january),settlement_date='2026-10-02'),path=self.path)
        with self.assertRaisesRegex(ValueError,'one opening'):
            positions.save_opening(self.january['position_id'],self.opening(self.february),path=self.path)
        self.assertEqual(positions.history(self.february['position_id'],self.path)['opening']['price_usd'],4)
        positions.save_opening(self.january['position_id'],self.opening(self.january,5),edit=True,path=self.path)
        self.assertEqual(positions.history(self.january['position_id'],self.path)['opening']['price_usd'],5)

    def test_cannot_allocate_stock_twice(self):
        with self.assertRaisesRegex(ValueError,'unallocated'):
            positions.create(dict(account='RRSP',symbol='RKLB',shares=100,contracts=1,strike=21,expiry='2028-03-17'),self.pool,path=self.path)
        with self.assertRaisesRegex(ValueError,'exceeds'):
            positions.allocate(self.january['position_id'],1100,self.pool,self.path)
        self.assertEqual(positions.availability(self.pool,self.path)[0]['available_shares'],0)

    def test_historical_opening_requires_checkbox_and_preserves_active_call(self):
        import position_history
        pid=self.january['position_id']
        original=dict(expiry='2025-03-21',strike=24,contracts=10,settlement_date='2025-03-04',price_usd=.8,reviewed=True)
        for override in [False,'true',1]:
            with self.assertRaisesRegex(ValueError,'original-before-rollovers'):
                positions.save_opening(pid,dict(original,historical_opening=override),path=self.path)
        for invalid in [dict(contracts=9),dict(reviewed=False),dict(settlement_date='2025-03-22')]:
            with self.assertRaises(ValueError):
                positions.save_opening(pid,dict(original,historical_opening=True,**invalid),path=self.path)
        saved=positions.save_opening(pid,dict(original,historical_opening=True),path=self.path)
        self.assertTrue(saved['historical_opening'])
        with self.assertRaisesRegex(ValueError,'one opening'):
            positions.save_opening(pid,dict(original,historical_opening=True),path=self.path)
        def accounting():
            history=positions.history(pid,self.path)
            self.assertEqual(history['position']['call_expiry'],'2028-01-21')
            self.assertEqual(history['position']['call_strike_native_currency'],20)
            return position_history.resolve('RRSP','RKLB',dict(expiry='2028-01-21',strike=20),10,[history['opening']],history['rollovers'])
        self.assertIsNone(accounting()['historical_option_net_usd'])
        roll=dict(settlement_date='2025-03-20',contracts=10,buyback_expiry='2025-03-21',buyback_strike=24,
                  buyback_price_usd=.4,sale_expiry='2026-01-16',sale_strike=22,sale_price_usd=1.2,fees_usd=10,reviewed=True)
        with self.assertRaises(ValueError):
            positions.save_rollover(pid,dict(roll,buyback_expiry='2028-01-21',buyback_strike=20),self.path)
        positions.save_rollover(pid,roll,self.path)
        self.assertIsNone(accounting()['historical_option_net_usd'])
        # Two rollovers on the same day retain entry order independent of random IDs.
        second=dict(roll,buyback_expiry='2026-01-16',buyback_strike=22,buyback_price_usd=.5,
                    sale_expiry='2028-01-21',sale_strike=20,sale_price_usd=2)
        positions.save_rollover(pid,second,self.path)
        self.assertEqual(accounting()['historical_option_net_usd'],3080)
        self.assertEqual(accounting()['rollover_count'],2)
        with self.assertRaises(ValueError): positions.save_rollover(pid,second,self.path)
        positions.save_rollover(pid,dict(second,settlement_date='2026-10-26',buyback_expiry='2028-01-21',buyback_strike=20,
                                        sale_expiry='2028-03-17',sale_strike=26),self.path)
        self.assertEqual(positions.history(pid,self.path)['position']['call_expiry'],'2028-03-17')
        self.assertEqual(positions.history(self.february['position_id'],self.path)['rollovers'],[])

    def test_rollover_moves_one_current_contract_and_preserves_identity(self):
        positions.save_opening(self.january['position_id'],self.opening(self.january),path=self.path)
        body=dict(settlement_date='2026-10-26',contracts=10,buyback_expiry='2028-01-21',buyback_strike=20,
                  buyback_price_usd=2,sale_expiry='2028-03-17',sale_strike=25,sale_price_usd=3,fees_usd=10,reviewed=True)
        positions.save_rollover(self.january['position_id'],body,self.path)
        saved=positions.history(self.january['position_id'],self.path)
        self.assertEqual(saved['position']['position_id'],self.january['position_id'])
        self.assertEqual(saved['position']['call_expiry'],'2028-03-17')
        self.assertEqual(len(saved['rollovers']),1)
        self.assertEqual(positions.history(self.february['position_id'],self.path)['rollovers'],[])
        with self.assertRaises(ValueError): positions.save_rollover(self.january['position_id'],body,self.path)
        self.assertEqual(len(positions.history(self.january['position_id'],self.path)['rollovers']),1)

    def test_closing_january_does_not_hide_february(self):
        january=positions.history(self.january['position_id'],self.path)['position']
        closed_holdings.save(dict(account='RRSP',symbol='RKLB',position_key=january['position_key'],close_date='2026-10-27',
                                 stock_price_usd=30,buyback_price_usd=2,fees_usd=0,reviewed=True,position_revision=january['position_revision']),january,{},self.path)
        again=positions.synchronize([self.raw],self.path)
        closed={r['position_key'] for r in closed_holdings.records(self.path)}
        self.assertEqual([h['position_id'] for h in again if h['position_id'] not in closed],[self.february['position_id']])
        self.assertEqual(positions.availability(self.pool,self.path)[0]['available_shares'],0)

    def test_no_shared_capture_for_other_expiry(self):
        import exit_optimizer as optimizer
        root=Path(self.folder.name);(root/'reports').mkdir()
        january=positions.history(self.january['position_id'],self.path)['position']
        source=dict(inputs=dict(account='RRSP',symbol='RKLB',shares=1000,contracts=10,held=dict(expiry='2028-01-21',strike=20)),result={})
        (root/'reports/exit-optimizer-rrsp-rklb.json').write_text(json.dumps(source))
        with patch.object(optimizer,'ROOT',root),patch.object(optimizer,'holdings',return_value=[january,self.february]),patch.object(optimizer,'reaccount_capture',side_effect=lambda value:value):
            first=optimizer.load_capture(dict(account='RRSP',symbol='RKLB',position_id=january['position_id']))
            self.assertEqual(first['inputs']['position_id'],january['position_id'])
            self.assertIsNone(optimizer.load_capture(dict(account='RRSP',symbol='RKLB',position_id=self.february['position_id'])))
            with self.assertRaisesRegex(ValueError,'multiple'):
                optimizer.load_capture(dict(account='RRSP',symbol='RKLB'))

    def test_concurrent_allocations_and_openings_cannot_double_count(self):
        from concurrent.futures import ThreadPoolExecutor
        enlarged={('RRSP','RKLB'):3000}
        def allocate(index):
            try:
                return positions.create(dict(account='RRSP',symbol='RKLB',shares=1000,contracts=10,strike=25+index,expiry='2028-04-21'),enlarged,path=self.path)['position_id']
            except ValueError: return None
        with ThreadPoolExecutor(max_workers=2) as executor: results=list(executor.map(allocate,[0,1]))
        self.assertEqual(sum(value is not None for value in results),1)
        def opening(index):
            try:
                positions.save_opening(self.january['position_id'],dict(self.opening(self.january),settlement_date=f'2026-10-0{index+1}'),path=self.path)
                return True
            except ValueError: return False
        with ThreadPoolExecutor(max_workers=2) as executor: results=list(executor.map(opening,[0,1]))
        self.assertEqual(sum(results),1)

    def test_stock_pool_cannot_be_reduced_below_allocations(self):
        import stock_basis
        with self.assertRaisesRegex(ValueError,'already allocated'):
            stock_basis.save_many([dict(account='RRSP',symbol='RKLB',currency='USD',quantity=1000,totalCost=20000)],self.path)

    def test_legacy_openings_for_two_expiries_are_claimed_separately(self):
        import option_premiums
        path=Path(self.folder.name)/'legacy.sqlite3'
        january=dict(self.raw,shares=1000)
        february=dict(january,call_expiry='2028-02-18')
        opening=dict(account='RRSP',symbol='RKLB',expiry='2028-01-21',strike=20,contracts=10,settlement_date='2026-10-01',price_usd=3,reviewed=True)
        option_premiums.save_usd(opening,path)
        option_premiums.save_usd(dict(opening,expiry='2028-02-18',price_usd=4),path)
        imported=positions.synchronize([january,february],path)
        by_expiry={h['call_expiry']:positions.history(h['position_id'],path)['opening'] for h in imported}
        self.assertEqual(by_expiry['2028-01-21']['price_usd'],3)
        self.assertEqual(by_expiry['2028-02-18']['price_usd'],4)
        self.assertNotEqual(by_expiry['2028-01-21']['_source'],by_expiry['2028-02-18']['_source'])
        self.assertEqual(len(option_premiums.usd_records(path)),2)
        self.assertEqual(len(positions.synchronize([january,february],path)),2)

    def test_missing_legacy_opening_can_be_entered_at_chain_root(self):
        import option_rollovers
        path=Path(self.folder.name)/'partial.sqlite3'
        row=dict(self.raw,shares=1000,call_expiry='2028-03-17',call_strike_native_currency=25)
        option_rollovers.save(dict(account='RRSP',symbol='RKLB',contracts=10,settlement_date='2026-10-26',
            buyback_expiry='2028-01-21',buyback_strike=20,buyback_price_usd=2,sale_expiry='2028-03-17',sale_strike=25,sale_price_usd=3,fees_usd=0,reviewed=True),path)
        imported=positions.synchronize([row],path)[0]
        history=positions.history(imported['position_id'],path)
        self.assertIsNone(history['opening'])
        self.assertEqual(len(history['rollovers']),1)
        positions.save_opening(imported['position_id'],dict(expiry='2028-01-21',strike=20,contracts=10,settlement_date='2026-10-01',price_usd=3,reviewed=True),path=path)
        self.assertEqual(positions.history(imported['position_id'],path)['opening']['expiry'],'2028-01-21')

    def test_stale_close_cannot_sell_shares_after_reallocation(self):
        january=positions.history(self.january['position_id'],self.path)['position']
        changed=positions.allocate(january['position_id'],1100,{('RRSP','RKLB'):2100},self.path)
        body=dict(account='RRSP',symbol='RKLB',position_key=january['position_key'],position_revision=january['position_revision'],
                  close_date='2026-10-27',stock_price_usd=30,buyback_price_usd=2,fees_usd=0,reviewed=True)
        with self.assertRaisesRegex(ValueError,'position changed'):
            closed_holdings.save(body,changed,{},self.path)
        self.assertEqual(closed_holdings.records(self.path),[])

    def test_new_position_has_standard_multiplier_and_fractional_strike_matches(self):
        from questrade_quotes import call_id
        h=positions.create(dict(account='RRSP',symbol='RKLB',shares=1000,contracts=10,strike=20.1,expiry='2028-03-17'),
                           {('RRSP','RKLB'):3000},path=self.path)
        self.assertEqual(h['contract_multiplier'],100)
        chain=dict(options=[dict(expiryDate='2028-03-17',chainPerRoot=[dict(root='RKLB',multiplier=100,
                   chainPerStrikePrice=[dict(strikePrice=20.1,callSymbolId=123)])])])
        self.assertEqual(call_id(chain,h),123)
