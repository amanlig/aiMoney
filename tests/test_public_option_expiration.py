from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
import tempfile
import unittest
import covered_positions as positions
import closed_holdings


class OptionExpirationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'expiry.sqlite3'
        self.raw=dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2026-10-23',call_strike_native_currency=20)
        self.holding=positions.synchronize([self.raw],self.path)[0]
        self.opening=dict(expiry='2026-10-23',strike=20,contracts=10,settlement_date='2026-10-01',price_usd=3,reviewed=True)
        positions.save_opening(self.holding['position_id'],self.opening,path=self.path)
        self.body=dict(fees_usd=2,reviewed=True,position_revision=self.holding['position_revision'])
        self.pool={('RRSP','RKLB'):1000}

    def expire(self,**changes):
        return positions.expire_worthless(self.holding['position_id'],dict(self.body,**changes),self.path,today=date(2026,10,27))

    def test_zero_buyback_realized_option_pl_and_retained_shares(self):
        preview=positions.expiration_preview(self.holding['position_id'],self.path,today=date(2026,10,27))
        self.assertTrue(preview['can_mark_expired'])
        self.assertEqual(preview['historical_option_net_usd'],3000)
        row=self.expire()
        self.assertEqual(row['realized_option_pl_usd'],2998)
        self.assertEqual(row['cash_flow_usd'],-2)
        self.assertEqual(row['stock_sale_usd'],0)
        self.assertEqual(row['buyback_total_usd'],0)
        self.assertEqual(row['shares_retained'],1000)
        self.assertNotIn('stock_cost_usd',row['accounting'])
        self.assertEqual(closed_holdings.records(self.path),[])
        self.assertEqual(positions.history(self.holding['position_id'],self.path)['status'],'expired_worthless')

    def test_original_expiry_realizes_prior_cycle_without_finishing_current_call(self):
        path=Path(self.folder.name)/'original-expiry.sqlite3'
        raw=dict(self.raw,call_expiry='2028-01-21',call_strike_native_currency=25)
        current=positions.synchronize([raw],path)[0];pid=current['position_id']
        original=dict(expiry='2025-03-21',strike=24,contracts=10,settlement_date='2025-03-04',price_usd=.8,reviewed=True,historical_opening=True)
        positions.save_opening(pid,original,path=path)
        result=positions.save_opening(pid,dict(original,expired_worthless=True,expiration_fees_usd=10),edit=True,path=path)
        self.assertEqual(result['realized_option_pl_usd'],790)
        receipt=positions.expirations(path)[0]
        self.assertEqual(receipt['realized_option_pl_usd'],790)
        self.assertEqual(receipt['stock_sale_usd'],0)
        self.assertEqual(receipt['buyback_total_usd'],0)
        saved=positions.history(pid,path)
        self.assertEqual(saved['status'],'active')
        self.assertEqual(saved['position']['position_revision'],current['position_revision'])
        self.assertIsNone(saved['opening'])
        self.assertEqual(positions.prior_realized(pid,path)['prior_realized_option_usd'],790)
        self.assertEqual(positions.availability(self.pool,path)[0]['available_shares'],0)
        with self.assertRaisesRegex(ValueError,'already recorded'):
            positions.save_opening(pid,dict(original,expired_worthless=True),path=path)
        with self.assertRaises(ValueError):
            positions.save_opening(result['expiration_id'],dict(original,price_usd=2),edit=True,path=path)
        with self.assertRaisesRegex(ValueError,'follow the recorded'):
            positions.save_opening(pid,dict(self.opening,expiry='2028-01-21',strike=25,settlement_date='2025-03-01'),path=path)
        active=dict(self.opening,expiry='2028-01-21',strike=25,settlement_date='2025-04-01',price_usd=2)
        positions.save_opening(pid,active,path=path)
        positions.expire_worthless(pid,dict(self.body,fees_usd=0,position_revision=current['position_revision']),path,today=date(2028,1,22))
        new=positions.create(dict(account='RRSP',symbol='RKLB',shares=1000,contracts=10,strike=30,expiry='2029-01-19'),self.pool,path=path)
        # Each completed cycle follows the shares exactly once.
        self.assertEqual(positions.prior_realized(new['position_id'],path)['prior_realized_option_usd'],2790)
        self.assertEqual(next(r for r in positions.expirations(path) if r['id']==receipt['id']),receipt)

    def test_original_expiry_requires_past_date_confirmation_and_no_buyback(self):
        path=Path(self.folder.name)/'original-validation.sqlite3'
        current=positions.synchronize([dict(self.raw,call_expiry='2028-01-21',call_strike_native_currency=25)],path)[0]
        original=dict(expiry='2025-03-21',strike=24,contracts=10,settlement_date='2025-03-04',price_usd=.8,reviewed=True,expired_worthless=True)
        for changes in [dict(reviewed=False),dict(expiration_fees_usd=-1),dict(expiration_fees_usd=float('nan')),
                        dict(expiry='2027-01-15'),dict(expiry='2028-01-21',strike=25)]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):positions.save_opening(current['position_id'],dict(original,**changes),path=path)
                self.assertIsNone(positions.history(current['position_id'],path)['opening'])
                self.assertEqual(positions.expirations(path),[])
        positions.save_opening(current['position_id'],dict(original,expired_worthless=False,historical_opening=True),path=path)
        roll=dict(settlement_date='2025-03-20',contracts=10,buyback_expiry='2025-03-21',buyback_strike=24,
                  buyback_price_usd=.4,sale_expiry='2028-01-21',sale_strike=25,sale_price_usd=2,fees_usd=0,reviewed=True)
        positions.save_rollover(current['position_id'],roll,path)
        with self.assertRaisesRegex(ValueError,'no recorded buybacks'):
            positions.save_opening(current['position_id'],original,edit=True,path=path)
        self.assertEqual(positions.expirations(path),[])
        self.assertIsNotNone(positions.history(current['position_id'],path)['opening'])

    def test_released_shares_can_cover_new_call_without_old_profit_or_opening(self):
        self.expire()
        self.assertEqual(positions.availability(self.pool,self.path)[0]['available_shares'],1000)
        new=positions.create(dict(account='RRSP',symbol='RKLB',shares=1000,contracts=10,strike=25,expiry='2028-01-21'),self.pool,path=self.path)
        self.assertNotEqual(new['position_id'],self.holding['position_id'])
        self.assertIsNone(positions.history(new['position_id'],self.path)['opening'])
        self.assertEqual(positions.availability(self.pool,self.path)[0]['available_shares'],0)
        with self.assertRaisesRegex(ValueError,'unallocated'):
            positions.create(dict(account='RRSP',symbol='RKLB',shares=100,contracts=1,strike=26,expiry='2028-01-21'),self.pool,path=self.path)

    def test_retained_stock_stays_selectable_and_next_call_preserves_all_realized_cycles(self):
        import stock_basis
        stock_basis.save_many([dict(account='RRSP',symbol='RKLB',currency='USD',quantity=1000,date='2025-01-02',priceUsd=20,feesUsd=10,totalCost=20010)],self.path)
        original_basis=stock_basis.records(self.path)
        receipt=positions.expire_worthless(self.holding['position_id'],self.body,self.path,today=date(2026,10,27),retain_stock=True,raw=[self.raw])
        retained=receipt['retained_position']
        self.assertEqual(retained['shares'],1000)
        self.assertEqual(retained['call_contracts'],0)
        self.assertEqual(retained['stock_purchase']['priceUsd'],20)
        self.assertIsNone(positions.history(retained['position_id'],self.path)['opening'])
        self.assertEqual(stock_basis.records(self.path),original_basis)
        self.assertEqual(positions.prior_realized(retained['position_id'],self.path)['prior_realized_option_usd'],2998)
        self.assertEqual(positions.retain_stock_holdings([self.raw],self.path),[])
        frozen=positions.expirations(self.path)
        positions.save_opening(retained['position_id'],dict(self.opening,expiry='2028-01-21',strike=25,settlement_date='2026-10-26',price_usd=2),path=self.path)
        current=positions.history(retained['position_id'],self.path)['position']
        second=positions.expire_worthless(current['position_id'],dict(self.body,fees_usd=1,position_revision=current['position_revision']),self.path,today=date(2028,1,22),retain_stock=True,raw=[self.raw])
        self.assertEqual(positions.prior_realized(second['retained_position']['position_id'],self.path)['prior_realized_option_usd'],4997)
        self.assertEqual(next(r for r in positions.expirations(self.path) if r['id']==frozen[0]['id']),frozen[0])

    def test_older_missing_stock_is_restored_once_and_can_split_for_another_call(self):
        self.expire(fees_usd=0)
        frozen=positions.expirations(self.path)
        restored=positions.retain_stock_holdings([self.raw],self.path)
        self.assertEqual(len(restored),1)
        stock=restored[0]
        self.assertEqual(stock['call_contracts'],0)
        self.assertEqual(positions.retain_stock_holdings([self.raw],self.path),[])
        positions.allocate(stock['position_id'],500,self.pool,self.path)
        self.assertEqual(positions.retain_stock_holdings([self.raw],self.path),[])
        other=positions.create(dict(account='RRSP',symbol='RKLB',shares=500,contracts=5,strike=25,expiry='2028-01-21'),self.pool,path=self.path)
        self.assertEqual(positions.prior_realized(stock['position_id'],self.path)['prior_realized_option_usd'],1500)
        self.assertEqual(positions.prior_realized(other['position_id'],self.path)['prior_realized_option_usd'],1500)
        self.assertEqual(positions.expirations(self.path),frozen)

    def test_recovery_only_keeps_unused_shares_and_respects_deleted_holdings(self):
        import holding_records
        self.expire(fees_usd=0)
        other=positions.create(dict(account='RRSP',symbol='RKLB',shares=500,contracts=5,strike=25,expiry='2028-01-21'),self.pool,path=self.path)
        restored=positions.retain_stock_holdings([self.raw],self.path)
        self.assertEqual(len(restored),1)
        self.assertEqual(restored[0]['shares'],500)
        before=positions.prior_realized(other['position_id'],self.path)
        holding_records.delete(restored[0]['position_id'],dict(confirmed=True,position_revision=restored[0]['position_revision']),self.path)
        self.assertEqual(positions.retain_stock_holdings([self.raw],self.path),[])
        self.assertEqual(positions.prior_realized(other['position_id'],self.path),before)

    def test_reported_rklb_history_retains_1000_shares_and_4466_10_realized(self):
        import holding_records
        path=Path(self.folder.name)/'reported-rklb.sqlite3'
        stock=holding_records.create(dict(account='RRSP',symbol='RKLB',purchase_date='2025-01-02',shares=1000,price_usd=21.4581,fees_usd=0),path)
        pid=stock['position_id']
        for expiry,strike,day,price in [('2025-03-21',24,'2025-03-04',.8),('2025-04-25',23,'2025-04-10',.95),('2025-05-09',25,'2025-04-29',.81)]:
            positions.save_opening(pid,dict(expiry=expiry,strike=strike,contracts=10,settlement_date=day,price_usd=price,reviewed=True,expired_worthless=True),path=path)
        positions.save_opening(pid,dict(expiry='2025-05-30',strike=23,contracts=10,settlement_date='2025-05-13',price_usd=.65,reviewed=True),path=path)
        for day,buy_exp,buy_strike,buy_price,sale_exp,sale_strike,sale_price in [('2025-05-29','2025-05-30',23,6.8,'2025-07-18',23,7.72),('2025-06-30','2025-07-18',23,13.59,'2025-10-17',24,13.99)]:
            positions.save_rollover(pid,dict(settlement_date=day,contracts=10,buyback_expiry=buy_exp,buyback_strike=buy_strike,buyback_price_usd=buy_price,sale_expiry=sale_exp,sale_strike=sale_strike,sale_price_usd=sale_price,fees_usd=31.95,reviewed=True),path)
        current=positions.history(pid,path)['position']
        receipt=positions.expire_worthless(pid,dict(reviewed=True,fees_usd=0,position_revision=current['position_revision']),path,retain_stock=True)
        self.assertEqual(receipt['realized_option_pl_usd'],1906.10)
        retained=receipt['retained_position']
        self.assertEqual(retained['shares'],1000)
        self.assertEqual(retained['call_contracts'],0)
        self.assertEqual(retained['stock_purchase']['priceUsd'],21.4581)
        self.assertEqual(positions.prior_realized(retained['position_id'],path)['prior_realized_option_usd'],4466.10)
        self.assertEqual(len(positions.expirations(path)),4)
        self.assertEqual(positions.retain_stock_holdings(path=path),[])

    def test_recorded_rollover_current_call_includes_all_legs_and_can_realize_loss(self):
        for price,buyback,sale,expected in [(3,2,4,4988),(1,6,2,-3012)]:
            with self.subTest(price=price):
                path=Path(self.folder.name)/f'roll-{price}.sqlite3'
                raw=dict(self.raw,call_expiry='2026-09-18')
                h=positions.synchronize([raw],path)[0]
                positions.save_opening(h['position_id'],dict(self.opening,expiry='2026-09-18',settlement_date='2026-08-01',price_usd=price),path=path)
                positions.save_rollover(h['position_id'],dict(contracts=10,settlement_date='2026-09-01',buyback_expiry='2026-09-18',buyback_strike=20,buyback_price_usd=buyback,sale_expiry='2026-10-23',sale_strike=25,sale_price_usd=sale,fees_usd=10,reviewed=True),path)
                current=positions.history(h['position_id'],path)['position']
                result=positions.expire_worthless(h['position_id'],dict(self.body,position_revision=current['position_revision']),path,today=date(2026,10,27))
                self.assertEqual(result['realized_option_pl_usd'],expected)
                self.assertEqual(result['accounting']['rollover_count'],1)
                self.assertEqual(result['strike'],25)
                self.assertEqual(result['buyback_total_usd'],0)

    def test_review_fees_date_and_stale_state_are_validated(self):
        for patch in [dict(reviewed=False),dict(fees_usd=-1),dict(fees_usd=float('nan')),dict(position_revision='old')]:
            with self.subTest(patch=patch):
                with self.assertRaises(ValueError): self.expire(**patch)
        for today in [date(2026,10,22),date(2026,10,23)]:
            with self.assertRaisesRegex(ValueError,'after the expiry date'):
                positions.expire_worthless(self.holding['position_id'],self.body,self.path,today=today)
        self.assertEqual(positions.expirations(self.path),[])
        current=positions.allocate(self.holding['position_id'],1100,{('RRSP','RKLB'):2000},self.path)
        with self.assertRaisesRegex(ValueError,'position changed'): self.expire()
        self.assertEqual(current['shares'],1100)

    def test_duplicate_and_finished_position_mutations_do_not_release_twice(self):
        self.expire()
        with self.assertRaisesRegex(ValueError,'already marked'): self.expire()
        with self.assertRaises(ValueError): positions.allocate(self.holding['position_id'],1000,self.pool,self.path)
        with self.assertRaises(ValueError): positions.save_opening(self.holding['position_id'],self.opening,edit=True,path=self.path)
        self.assertEqual(len(positions.expirations(self.path)),1)
        self.assertEqual(positions.availability(self.pool,self.path)[0]['available_shares'],1000)
        self.assertEqual(positions.synchronize([self.raw],self.path)[0]['option_expired'],True)

    def test_close_and_expiration_are_mutually_exclusive_under_concurrency(self):
        close=dict(account='RRSP',symbol='RKLB',position_key=self.holding['position_key'],position_revision=self.holding['position_revision'],close_date='2026-10-27',stock_price_usd=30,buyback_price_usd=2,fees_usd=0,reviewed=True)
        def finish(action):
            try:
                if action=='expire': self.expire()
                else: closed_holdings.save(close,self.holding,{},self.path)
                return True
            except ValueError: return False
        with ThreadPoolExecutor(max_workers=2) as executor: results=list(executor.map(finish,['expire','close']))
        self.assertEqual(sum(results),1)
        expired=positions.expirations(self.path);closed=closed_holdings.records(self.path)
        self.assertEqual(len(expired)+len(closed),1)
        self.assertEqual(positions.availability(self.pool,self.path)[0]['available_shares'],1000 if expired else 0)

    def test_missing_history_is_not_invented_and_report_is_frozen(self):
        positions.save_opening(self.holding['position_id'],self.opening,edit=True,path=self.path)
        first=self.expire(fees_usd=0)
        self.assertEqual(first['realized_option_pl_usd'],3000)
        self.assertEqual(first['cash_flow_usd'],0)
        self.assertEqual(positions.expirations(self.path)[0]['accounting'],first['accounting'])
        path=Path(self.folder.name)/'missing.sqlite3'
        h=positions.synchronize([self.raw],path)[0]
        row=positions.expire_worthless(h['position_id'],dict(self.body,position_revision=h['position_revision']),path,today=date(2026,10,27))
        self.assertIsNone(row['realized_option_pl_usd'])
        self.assertEqual(row['shares_retained'],1000)

    def test_expiration_does_not_change_other_expiry_or_stock_cost(self):
        import stock_basis
        stock_basis.save_many([dict(account='RRSP',symbol='RKLB',currency='USD',quantity=2000,totalCost=40000)],self.path)
        other=positions.create(dict(account='RRSP',symbol='RKLB',shares=1000,contracts=10,strike=20,expiry='2028-02-18'),{('RRSP','RKLB'):2000},path=self.path)
        self.expire()
        self.assertEqual(positions.history(other['position_id'],self.path)['status'],'active')
        self.assertEqual(positions.availability({('RRSP','RKLB'):2000},self.path)[0]['available_shares'],1000)
        self.assertEqual(stock_basis.get('RRSP','RKLB','USD',self.path)['totalCost'],40000)
