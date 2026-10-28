"""Integration checks against a disposable PostgreSQL database only."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import option_premiums
import optimizer_assessments
import fx_samples
import stock_basis
from database import connect
from migrate_postgres import initialize, migrate


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL to a disposable PostgreSQL database')
class PostgreSQLTests(unittest.TestCase):
    def test_migration_and_application_operations(self):
        url = os.environ['TEST_DATABASE_URL']
        with connect(url=url) as db:
            initialize(db)
            db.execute('TRUNCATE deleted_share_sources, deleted_position_sources, position_share_sources, option_expirations, covered_position_rollovers, covered_positions, closed_holdings, option_rollovers, samples, stock_cost_basis, option_premiums, option_premium_sales_usd, recommendation_runs RESTART IDENTITY')
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.sqlite3'
            stock_basis.save_many([dict(account='LIRA', symbol='TEST', currency='USD', quantity=100, totalCost=1000)], source)
            with sqlite3.connect(source) as db:
                db.execute('UPDATE stock_cost_basis SET id=42')
            fx = dict(account='TFSA',symbol='TEST',instrument='option',action='buy',direction='buy_usd',settlement_date='2025-05-27',trade_date=None,usd_amount=1001,commission_usd=1,cad_amount=1401.4,applied_rate=1.4,notes='Unicode café',reviewed=True)
            fx_samples.save(fx, source, lookup=lambda _: 1.39)
            sale = dict(account='LIRA',symbol='TEST',expiry='2028-01-21',strike=40,contracts=1,settlement_date='2025-05-27',price_usd=2,reviewed=True)
            option_premiums.save_usd(sale, source)
            option_premiums.save(dict(sale,symbol='OTHER',fees_usd=0,fx=1.4,net_cad=280), source)
            with connect(source) as db:
                initialize(db)
                db.insert_id('INSERT INTO recommendation_runs (created_at,model,prompt_version,snapshot_json,assessment,response_id,usage_json) VALUES (?,?,?,?,?,?,?)', ('2025-05-27','test',optimizer_assessments.PROMPT_VERSION,'{}','saved café',None,'{}'))
            import covered_positions
            imported=covered_positions.synchronize([dict(account='LIRA',symbol='TEST',shares=100,call_contracts=1,call_expiry='2028-01-21',call_strike_native_currency=40)],source)[0]
            covered_positions.save_rollover(imported['position_id'],dict(contracts=1,settlement_date='2025-06-01',buyback_expiry='2028-01-21',buyback_strike=40,buyback_price_usd=1,sale_expiry='2026-01-16',sale_strike=45,sale_price_usd=3,fees_usd=0,reviewed=True),source)
            current=covered_positions.history(imported['position_id'],source)['position']
            covered_positions.expire_worthless(imported['position_id'],dict(fees_usd=1,reviewed=True,position_revision=current['position_revision']),source)
            following=covered_positions.create(dict(account='LIRA',symbol='TEST',shares=100,contracts=1,strike=50,expiry='2028-03-17'),{('LIRA','TEST'):100},path=source)
            with connect(source) as db:
                db.execute("INSERT INTO deleted_position_sources(source_key,deleted_at) VALUES ('deleted-import','now')")
                db.execute("INSERT INTO deleted_share_sources(id,created_at,links_json) VALUES ('deleted-child','now','[]')")
            before = source.read_bytes()
            counts = migrate(source, url)
            self.assertEqual(counts['stock_cost_basis'], 1)
            self.assertEqual(counts['covered_positions'],2)
            self.assertEqual(counts['position_share_sources'],2)
            self.assertEqual(counts['covered_position_rollovers'],1)
            self.assertEqual(counts['option_expirations'],1)
            self.assertEqual(counts['deleted_position_sources'],1)
            self.assertEqual(counts['deleted_share_sources'],1)
            self.assertEqual(migrate(source, url), counts)
            self.assertEqual(source.read_bytes(), before)
            with patch.dict(os.environ, DATABASE_URL=url):
                self.assertEqual(stock_basis.get('LIRA', 'TEST', 'USD')['id'], 42)
                self.assertEqual(covered_positions.history(imported['position_id'])['opening']['price_usd'],2)
                self.assertEqual(len(covered_positions.history(imported['position_id'])['rollovers']),1)
                self.assertEqual(covered_positions.expirations()[0]['realized_option_pl_usd'],399)
                self.assertEqual(covered_positions.prior_realized(following['position_id'])['prior_realized_option_usd'],399)
                rows = stock_basis.save_many([dict(account='LIRA', symbol='NEXT', currency='USD', quantity=10, totalCost=200)])
                self.assertGreater(next(r['id'] for r in rows if r['symbol']=='NEXT'), 42)
                self.assertEqual(fx_samples.records()[0]['notes'], 'Unicode café')
                self.assertEqual(optimizer_assessments.history()[0]['assessment'], 'saved café')
                saved = option_premiums.save_usd(dict(sale, symbol='NEW'))
                self.assertGreater(saved['id'], 1)
                with self.assertRaisesRegex(ValueError, 'already recorded'):
                    option_premiums.save_usd(dict(sale, symbol='NEW'))
                with self.assertRaisesRegex(ValueError, 'already recorded'):
                    option_premiums.save_usd(dict(sale, symbol='OTHER'))
                new_fx = fx_samples.save(dict(fx, notes='new', symbol='NEXT'), lookup=lambda _: 1.4)
                self.assertGreater(new_fx['id'], 1)
                with self.assertRaisesRegex(ValueError, 'already saved'):
                    fx_samples.save(dict(fx, symbol='NEXT'), lookup=lambda _: 1.4)
                with self.assertRaises(Exception):
                    with connect(readonly=True) as readonly:
                        readonly.execute('DELETE FROM samples')
                stock_basis.save_many([dict(account='LIRA', symbol='TEST', currency='USD', quantity=100, totalCost=1100)])
                self.assertEqual(stock_basis.get('LIRA', 'TEST', 'USD')['totalCost'], 1100)
            with self.assertRaises(ValueError):
                migrate(source, url)
            with connect(url=url) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM stock_cost_basis').fetchone()['n'], 2)
                with self.assertRaises(RuntimeError):
                    with connect(url=url) as transaction:
                        transaction.execute('DELETE FROM stock_cost_basis')
                        raise RuntimeError('rollback')
                self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM stock_cost_basis').fetchone()['n'], 2)

    def test_rollover_and_closed_holdings_persistence(self):
        import option_rollovers
        import closed_holdings
        with patch.dict(os.environ, DATABASE_URL=os.environ['TEST_DATABASE_URL']):
            roll = option_rollovers.save(dict(account='RRSP', symbol='ROLLTEST', settlement_date='2026-10-26', contracts=1,
                buyback_expiry='2027-01-15', buyback_strike=25, buyback_price_usd=2,
                sale_expiry='2028-01-21', sale_strike=30, sale_price_usd=3, fees_usd=5, reviewed=True))
            self.assertEqual(roll['net_cash_usd'], 95)
            self.assertEqual(option_rollovers.records()[0]['id'], roll['id'])
            holding=dict(account='RRSP', symbol='ROLLTEST', shares=100, call_contracts=1,
                         call_expiry='2028-01-21', call_strike_native_currency=30)
            body=dict(account='RRSP', symbol='ROLLTEST', position_key=closed_holdings.position_key(holding), close_date='2026-10-27',
                      stock_price_usd=40, buyback_price_usd=3, fees_usd=5, reviewed=True)
            reference=dict(stock_cost_usd=2000, historical_option_net_usd=395, rollover_count=1)
            row=closed_holdings.save(body, holding, reference)
            self.assertEqual(row['realized_pl_usd'], 2090)
            self.assertEqual(closed_holdings.records()[0]['position'], holding)
            with self.assertRaisesRegex(ValueError, 'already closed'):
                closed_holdings.save(body, holding, reference)

    def test_stable_positions_one_opening_and_separate_expiries(self):
        import covered_positions as positions
        import closed_holdings
        with patch.dict(os.environ,DATABASE_URL=os.environ['TEST_DATABASE_URL']):
            raw=dict(account='RRSP',symbol='RKLBTEST',shares=2000,call_contracts=10,call_expiry='2028-01-21',call_strike_native_currency=20)
            january=next(h for h in positions.synchronize([raw]) if h['symbol']=='RKLBTEST')
            pool={('RRSP','RKLBTEST'):2000}
            january=positions.allocate(january['position_id'],1000,pool)
            february=positions.create(dict(account='RRSP',symbol='RKLBTEST',shares=1000,contracts=10,strike=20,expiry='2028-02-18'),pool)
            opening=dict(expiry='2028-01-21',strike=20,contracts=10,settlement_date='2026-10-01',price_usd=3,reviewed=True)
            positions.save_opening(january['position_id'],opening)
            positions.save_opening(february['position_id'],dict(opening,expiry='2028-02-18',price_usd=4))
            with self.assertRaisesRegex(ValueError,'one opening'):
                positions.save_opening(january['position_id'],dict(opening,settlement_date='2026-10-02'))
            with self.assertRaisesRegex(ValueError,'unallocated'):
                positions.create(dict(account='RRSP',symbol='RKLBTEST',shares=100,contracts=1,strike=25,expiry='2028-03-17'),pool)
            close=dict(account='RRSP',symbol='RKLBTEST',position_key=january['position_key'],position_revision=january['position_revision'],close_date='2026-10-27',stock_price_usd=30,buyback_price_usd=2,fees_usd=0,reviewed=True)
            closed_holdings.save(close,january,dict(stock_cost_usd=20000,historical_option_net_usd=3000))
            self.assertEqual(positions.history(february['position_id'])['opening']['price_usd'],4)
            self.assertEqual(next(s for s in positions.availability(pool) if s['symbol']=='RKLBTEST')['available_shares'],0)


    def test_original_expiry_backfill_preserves_active_call_and_serializes_replays(self):
        from concurrent.futures import ThreadPoolExecutor
        import covered_positions as positions
        with patch.dict(os.environ,DATABASE_URL=os.environ['TEST_DATABASE_URL']):
            raw=dict(account='RRSP',symbol='ORIGEXPTEST',shares=1000,call_contracts=10,call_expiry='2028-01-21',call_strike_native_currency=25)
            current=next(h for h in positions.synchronize([raw]) if h['symbol']=='ORIGEXPTEST')
            body=dict(expiry='2025-03-21',strike=24,contracts=10,settlement_date='2025-03-04',price_usd=.8,reviewed=True,expired_worthless=True,expiration_fees_usd=10)
            def save(index):
                try:positions.save_opening(current['position_id'],body);return True
                except ValueError:return False
            with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(save,[0,1]))
            self.assertEqual(sum(results),1)
            receipts=[r for r in positions.expirations() if r['symbol']=='ORIGEXPTEST']
            self.assertEqual(len(receipts),1)
            self.assertEqual(receipts[0]['realized_option_pl_usd'],790)
            self.assertEqual(positions.history(current['position_id'])['position']['position_revision'],current['position_revision'])
            self.assertEqual(positions.history(current['position_id'])['status'],'active')
            self.assertIsNone(positions.history(current['position_id'])['opening'])
            self.assertEqual(positions.prior_realized(current['position_id'])['prior_realized_option_usd'],790)
            self.assertEqual(next(s for s in positions.availability({('RRSP','ORIGEXPTEST'):1000}) if s['symbol']=='ORIGEXPTEST')['available_shares'],0)

    def test_stock_first_and_delete_preserve_another_purchase(self):
        import covered_positions as positions
        import holding_records
        with patch.dict(os.environ,DATABASE_URL=os.environ['TEST_DATABASE_URL']):
            purchase=dict(account='RRSP',symbol='DELETESTOCK',purchase_date='2025-01-02',shares=100,price_usd=20,fees_usd=1)
            first=holding_records.create(purchase)
            second=holding_records.create(dict(purchase,price_usd=30))
            positions.save_opening(first['position_id'],dict(expiry='2025-05-30',strike=23,contracts=1,settlement_date='2025-05-13',price_usd=.65,reviewed=True))
            self.assertTrue(positions.history(first['position_id'])['position']['can_mark_expired'])
            self.assertFalse(any(r['id']==first['position_id'] for r in positions.expirations()))
            positions.save_rollover(first['position_id'],dict(settlement_date='2025-05-20',contracts=1,buyback_expiry='2025-05-30',buyback_strike=23,buyback_price_usd=.9,sale_expiry='2028-01-21',sale_strike=25,sale_price_usd=1.5,fees_usd=0,reviewed=True))
            current=positions.history(first['position_id'])['position']
            holding_records.delete(current['position_id'],dict(confirmed=True,position_revision=current['position_revision']))
            self.assertEqual(positions.history(second['position_id'])['position']['stock_purchase']['priceUsd'],30)
            self.assertEqual(stock_basis.get('RRSP','DELETESTOCK','USD')['quantity'],100)
            self.assertAlmostEqual(stock_basis.get('RRSP','DELETESTOCK','USD')['priceUsd'],30)
            raw=dict(account='TFSA',symbol='DELETEIMPORT',shares=100,call_contracts=1,call_expiry='2028-01-21',call_strike_native_currency=25)
            imported=next(h for h in positions.synchronize([raw]) if h['symbol']=='DELETEIMPORT')
            holding_records.delete(imported['position_id'],dict(confirmed=True,position_revision=imported['position_revision']))
            self.assertFalse(any(h['symbol']=='DELETEIMPORT' for h in positions.synchronize([raw])))

    def test_stock_stays_available_after_expiry_and_next_opening_keeps_realized_gain(self):
        import covered_positions as positions
        with patch.dict(os.environ,DATABASE_URL=os.environ['TEST_DATABASE_URL']):
            raw=dict(account='RRSP',symbol='KEEPSTOCK',shares=1000,call_contracts=10,call_expiry='2026-10-23',call_strike_native_currency=20)
            h=next(h for h in positions.synchronize([raw]) if h['symbol']=='KEEPSTOCK')
            positions.save_opening(h['position_id'],dict(expiry='2026-10-23',strike=20,contracts=10,settlement_date='2026-10-01',price_usd=3,reviewed=True))
            result=positions.expire_worthless(h['position_id'],dict(reviewed=True,fees_usd=2,position_revision=h['position_revision']),retain_stock=True,raw=[raw])
            stock=result['retained_position']
            self.assertEqual(stock['shares'],1000)
            self.assertEqual(stock['call_contracts'],0)
            self.assertEqual(positions.prior_realized(stock['position_id'])['prior_realized_option_usd'],2998)
            self.assertEqual(positions.retain_stock_holdings([raw]),[])
            positions.save_opening(stock['position_id'],dict(expiry='2028-01-21',strike=25,contracts=10,settlement_date='2026-10-26',price_usd=2,reviewed=True))
            self.assertEqual(positions.prior_realized(stock['position_id'])['prior_realized_option_usd'],2998)

    def test_worthless_expiry_retains_and_releases_shares_once(self):
        from concurrent.futures import ThreadPoolExecutor
        import covered_positions as positions
        with patch.dict(os.environ,DATABASE_URL=os.environ['TEST_DATABASE_URL']):
            raw=dict(account='RRSP',symbol='EXPIRYTEST',shares=1000,call_contracts=10,call_expiry='2026-10-23',call_strike_native_currency=20)
            h=next(h for h in positions.synchronize([raw]) if h['symbol']=='EXPIRYTEST')
            positions.save_opening(h['position_id'],dict(expiry='2026-10-23',strike=20,contracts=10,settlement_date='2026-10-01',price_usd=3,reviewed=True))
            body=dict(fees_usd=2,reviewed=True,position_revision=h['position_revision'])
            def expire(index):
                try: positions.expire_worthless(h['position_id'],body);return True
                except ValueError:return False
            with ThreadPoolExecutor(max_workers=2) as executor: results=list(executor.map(expire,[0,1]))
            self.assertEqual(sum(results),1)
            record=next(r for r in positions.expirations() if r['symbol']=='EXPIRYTEST')
            self.assertEqual(record['realized_option_pl_usd'],2998)
            self.assertEqual(record['cash_flow_usd'],-2)
            pool={('RRSP','EXPIRYTEST'):1000}
            self.assertEqual(next(s for s in positions.availability(pool) if s['symbol']=='EXPIRYTEST')['available_shares'],1000)
            new=positions.create(dict(account='RRSP',symbol='EXPIRYTEST',shares=1000,contracts=10,strike=25,expiry='2028-01-21'),pool,h)
            self.assertNotEqual(new['position_id'],h['position_id'])
            self.assertFalse(new.get('option_expired',False))
            self.assertIsNone(positions.history(new['position_id'])['opening'])
            self.assertEqual(positions.prior_realized(new['position_id'])['prior_realized_option_usd'],2998)
