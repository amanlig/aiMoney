import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from database import connect
from database_schema import SCHEMA
import covered_positions as positions
import holding_records as records
import stock_basis


class HoldingRecordsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'holdings.sqlite3'
        self.reports=self.root/'reports';self.reports.mkdir()
        self.purchase=dict(account='RRSP',symbol='RKLB',purchase_date='2025-01-02',shares=1000,price_usd=20,fees_usd=10)

    def new(self,**changes):return records.create(dict(self.purchase,**changes),self.path)

    def remove(self,h,**changes):
        return records.delete(h['position_id'],dict(confirmed=True,position_revision=h['position_revision'],**changes),self.path,self.reports)

    def test_stock_first_then_opening_keeps_identity_and_separate_purchase_prices(self):
        first=self.new()
        self.assertEqual(first['call_contracts'],0)
        self.assertFalse(first['can_mark_expired'])
        second=self.new(shares=500,price_usd=30,fees_usd=5)
        self.assertEqual(positions.history(first['position_id'],self.path)['position']['stock_purchase']['priceUsd'],20)
        self.assertEqual(second['stock_purchase']['priceUsd'],30)
        opening=dict(expiry='2028-01-21',strike=25,contracts=10,settlement_date='2025-01-03',price_usd=2,reviewed=True)
        for changes in [dict(contracts=11),dict(settlement_date='2025-01-01'),dict(reviewed=False)]:
            with self.assertRaises(ValueError):positions.save_opening(first['position_id'],dict(opening,**changes),path=self.path)
        positions.save_opening(first['position_id'],opening,path=self.path)
        current=positions.history(first['position_id'],self.path)['position']
        self.assertEqual(current['position_id'],first['position_id'])
        self.assertEqual(current['call_contracts'],10)
        self.assertEqual(current['call_expiry'],'2028-01-21')
        self.assertEqual(positions.availability({},self.path)[0]['available_shares'],0)
        with self.assertRaisesRegex(ValueError,'one opening'):positions.save_opening(first['position_id'],opening,path=self.path)

    def test_delete_own_purchase_and_analysis_preserves_another_lot(self):
        first=self.new();second=self.new(shares=500,price_usd=30,fees_usd=5)
        captures={}
        with connect(self.path) as db:
            db.execute(SCHEMA['recommendation_runs'])
            for h in [first,second]:
                snapshot=dict(position=dict(position_id=h['position_id']))
                db.execute("INSERT INTO recommendation_runs(created_at,model,prompt_version,snapshot_json,assessment,usage_json) VALUES ('now','test','v1',?,'test','{}')",(json.dumps(snapshot),))
                file=self.reports/f"exit-optimizer-rrsp-rklb-{h['position_id']}.json"
                file.write_text(json.dumps(dict(inputs=dict(position_id=h['position_id']))));captures[h['position_id']]=file
        self.remove(first)
        self.assertFalse(captures[first['position_id']].exists())
        self.assertTrue(captures[second['position_id']].exists())
        self.assertEqual(positions.history(second['position_id'],self.path)['position']['stock_purchase']['priceUsd'],30)
        basis=stock_basis.get('RRSP','RKLB','USD',self.path)
        self.assertEqual(basis['quantity'],500)
        self.assertAlmostEqual(basis['priceUsd'],30)
        self.assertAlmostEqual(basis['feesUsd'],5)
        with connect(self.path) as db:self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM recommendation_runs').fetchone()['n'],1)

    def test_purchase_edit_and_optimizer_reference_use_the_selected_lot(self):
        import exit_optimizer
        first=self.new();self.new(shares=500,price_usd=30,fees_usd=5)
        records.update_purchase(first['position_id'],dict(self.purchase,price_usd=22,fees_usd=20),self.path)
        original_get=stock_basis.get
        saved=positions.history(first['position_id'],self.path);prior=positions.prior_realized(first['position_id'],self.path)
        with patch.object(exit_optimizer.stock_basis,'get',side_effect=lambda account,symbol,currency:original_get(account,symbol,currency,self.path)), \
             patch.object(exit_optimizer.covered_positions,'history',return_value=saved), \
             patch.object(exit_optimizer.covered_positions,'prior_realized',return_value=prior):
            ref=exit_optimizer.opening_reference('RRSP','RKLB',dict(expiry='2028-01-21',strike=25),1000,10,first['position_id'])
        self.assertEqual(ref['stock_price_usd'],22)
        self.assertEqual(ref['stock_cost_usd'],22020)

    def test_imported_holding_does_not_return_after_delete_or_recreate(self):
        raw=dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2028-01-21',call_strike_native_currency=25)
        h=positions.synchronize([raw],self.path)[0]
        self.remove(h)
        self.assertEqual(positions.synchronize([raw],self.path),[])
        new=self.new()
        self.assertNotEqual(new['position_id'],h['position_id'])
        self.assertEqual([r['position_id'] for r in positions.synchronize([raw],self.path)],[new['position_id']])
        self.remove(new)
        self.assertEqual(positions.synchronize([raw],self.path),[])
        self.assertEqual(stock_basis.records(self.path),[])

    def test_confirmation_stale_state_and_failure_do_not_delete_records(self):
        h=self.new();file=self.reports/f"exit-optimizer-rrsp-rklb-{h['position_id']}.json"
        file.write_text(json.dumps(dict(inputs=dict(position_id=h['position_id']))))
        for body in [dict(confirmed=False,position_revision=h['position_revision']),dict(confirmed=True,position_revision='old')]:
            with self.assertRaises(ValueError):records.delete(h['position_id'],body,self.path,self.reports)
        with patch.object(records,'save_pool',side_effect=ValueError('Synthetic failure')):
            with self.assertRaisesRegex(ValueError,'Synthetic failure'):self.remove(h)
        self.assertTrue(file.exists())
        self.assertEqual(positions.history(h['position_id'],self.path)['position'],h)

    def test_exclusive_expired_original_is_deleted_with_current_holding(self):
        h=self.new()
        positions.save_opening(h['position_id'],dict(expiry='2028-01-21',strike=25,contracts=10,settlement_date='2025-01-03',price_usd=2,reviewed=True),path=self.path)
        # Seed an earlier original in a separate imported fixture, as the existing entry flow does.
        raw=dict(account='TFSA',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2028-01-21',call_strike_native_currency=25)
        current=next(r for r in positions.synchronize([raw],self.path) if r['account']=='TFSA')
        result=positions.save_opening(current['position_id'],dict(expiry='2025-03-21',strike=24,contracts=10,settlement_date='2025-03-04',price_usd=.8,reviewed=True,expired_worthless=True),path=self.path)
        self.assertEqual(records.preview(current['position_id'],self.path)['expired_cycles'],1)
        self.remove(current)
        self.assertEqual(positions.expirations(self.path),[])
        with self.assertRaises(ValueError):positions.history(result['expiration_id'],self.path)
        self.assertIsNotNone(positions.history(h['position_id'],self.path)['opening'])

    def test_shared_ancestry_and_rounding_do_not_change_after_deleting_one_child(self):
        stock_basis.save_many([dict(account='RRSP',symbol='RKLB',currency='USD',quantity=1000,date='2025-01-02',priceUsd=20,feesUsd=10,totalCost=20010)],self.path)
        parent=positions.synchronize([dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2026-10-23',call_strike_native_currency=25)],self.path)[0]
        positions.save_opening(parent['position_id'],dict(expiry='2026-10-23',strike=25,contracts=10,settlement_date='2026-10-01',price_usd=3.00001,reviewed=True),path=self.path)
        parent=positions.history(parent['position_id'],self.path)['position']
        positions.expire_worthless(parent['position_id'],dict(fees_usd=0,reviewed=True,position_revision=parent['position_revision']),self.path,today=date(2026,10,27))
        pool={('RRSP','RKLB'):1000}
        first=positions.create(dict(account='RRSP',symbol='RKLB',shares=500,contracts=5,strike=25,expiry='2028-01-21'),pool,path=self.path)
        second=positions.create(dict(account='RRSP',symbol='RKLB',shares=500,contracts=5,strike=30,expiry='2028-01-21'),pool,path=self.path)
        before=positions.prior_realized(second['position_id'],self.path)
        self.remove(first)
        self.assertEqual(positions.prior_realized(second['position_id'],self.path),before)
        self.assertEqual(len(positions.expirations(self.path)),1)
        self.assertEqual(positions.availability(pool,self.path)[0]['available_shares'],0)
        self.remove(second)
        self.assertEqual(positions.expirations(self.path),[])
        with connect(self.path) as db:self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM deleted_share_sources').fetchone()['n'],0)

    def test_stock_first_can_record_expired_original_then_current_sale(self):
        h=self.new()
        result=positions.save_opening(h['position_id'],dict(expiry='2025-03-21',strike=24,contracts=10,settlement_date='2025-03-04',price_usd=.8,reviewed=True,expired_worthless=True),path=self.path)
        self.assertEqual(result['realized_option_pl_usd'],800)
        self.assertEqual(positions.history(h['position_id'],self.path)['position']['call_contracts'],0)
        positions.save_opening(h['position_id'],dict(expiry='2028-01-21',strike=25,contracts=10,settlement_date='2025-04-01',price_usd=2,reviewed=True),path=self.path)
        self.assertEqual(positions.prior_realized(h['position_id'],self.path)['prior_realized_option_usd'],800)

    def test_past_opening_can_be_rolled_without_being_marked_expired(self):
        import exit_optimizer
        import position_history
        h=self.new();pid=h['position_id']
        for expiry,strike,day,price in [('2025-03-21',24,'2025-03-04',.8),('2025-04-25',23,'2025-03-24',.95),('2025-05-09',25,'2025-04-28',.81)]:
            positions.save_opening(pid,dict(expiry=expiry,strike=strike,contracts=10,settlement_date=day,price_usd=price,reviewed=True,expired_worthless=True),path=self.path)
        before=positions.expirations(self.path)
        positions.save_opening(pid,dict(expiry='2025-05-30',strike=23,contracts=10,settlement_date='2025-05-13',price_usd=.65,reviewed=True,expired_worthless=False),path=self.path)
        pending=positions.history(pid,self.path)
        self.assertEqual(pending['opening']['gross_usd'],650)
        self.assertEqual(positions.expirations(self.path),before)
        self.assertEqual(positions.prior_realized(pid,self.path)['prior_realized_option_usd'],2560)
        with patch.object(exit_optimizer,'select_holding',return_value=pending['position']),patch.object(exit_optimizer,'public_fetch') as network:
            with self.assertRaisesRegex(ValueError,'historical call'):exit_optimizer.run(dict(account='RRSP',symbol='RKLB',position_id=pid))
        network.assert_not_called()
        positions.save_rollover(pid,dict(settlement_date='2025-05-20',contracts=10,buyback_expiry='2025-05-30',buyback_strike=23,buyback_price_usd=.9,
                                         sale_expiry='2028-01-21',sale_strike=25,sale_price_usd=1.5,fees_usd=0,reviewed=True),self.path)
        saved=positions.history(pid,self.path)
        self.assertEqual(saved['position']['call_expiry'],'2028-01-21')
        self.assertFalse(saved['position']['can_mark_expired'])
        self.assertEqual(positions.expirations(self.path),before)
        history=position_history.resolve('RRSP','RKLB',dict(expiry='2028-01-21',strike=25),10,[saved['opening']],saved['rollovers'])
        self.assertEqual(history['historical_option_net_usd'],1250)
        self.assertEqual(history['active_realized_option_usd'],-250)

    def test_purchase_validation_and_stock_only_optimization_guard(self):
        import exit_optimizer
        for changes in [dict(shares=0),dict(price_usd=-1),dict(fees_usd=-1),dict(purchase_date='2099-01-01'),dict(symbol='../bad')]:
            with self.assertRaises(ValueError):self.new(**changes)
        h=self.new()
        with patch.object(exit_optimizer,'select_holding',return_value=h),patch.object(exit_optimizer,'public_fetch') as network:
            with self.assertRaisesRegex(ValueError,'option opening sale'):exit_optimizer.run(dict(account='RRSP',symbol='RKLB',position_id=h['position_id']))
        network.assert_not_called()
