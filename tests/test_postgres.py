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
            db.execute('TRUNCATE samples, stock_cost_basis, option_premiums, option_premium_sales_usd, recommendation_runs RESTART IDENTITY')
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
            before = source.read_bytes()
            counts = migrate(source, url)
            self.assertEqual(counts['stock_cost_basis'], 1)
            self.assertEqual(migrate(source, url), counts)
            self.assertEqual(source.read_bytes(), before)
            with patch.dict(os.environ, DATABASE_URL=url):
                self.assertEqual(stock_basis.get('LIRA', 'TEST', 'USD')['id'], 42)
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
