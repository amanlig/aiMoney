import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import stock_basis


class BasisTests(unittest.TestCase):
    def sample(self):
        return dict(account='RRSP',symbol='TEST',currency='CAD',quantity=500,date='2024-10-08',priceUsd=25.115,feesUsd=6.95,fx=1.3855,totalCost=17408.05)

    def test_persist_average_and_update(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db.sqlite3'
            stock_basis.save_many([self.sample()],path)
            saved=stock_basis.get('RRSP','TEST',path=path)
            self.assertEqual(saved['averageCost'],34.8161)
            self.assertEqual(saved['cadTotal'],17408.05)
            stock_basis.save_many([dict(self.sample(),priceUsd=None,totalCost=18000)],path)
            self.assertEqual(len(stock_basis.records(path)),1)
            self.assertEqual(stock_basis.get('RRSP','TEST',path=path)['averageCost'],36)

    def test_invalid_batch_is_atomic(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db.sqlite3'
            stock_basis.save_many([self.sample()],path)
            for changes in [{'quantity':0},{'quantity':float('nan')},{'totalCost':100},{'fx':-1},{'date':'bad'}]:
                with self.assertRaises(ValueError):stock_basis.save_many([dict(self.sample(),symbol='OTHER'),dict(self.sample(),**changes)],path)
                self.assertEqual(len(stock_basis.records(path)),1)

    def test_migration_does_not_replace_later_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db.sqlite3';source=Path(folder)/'old.json'
            old=self.sample();old['cadTotal']=old.pop('totalCost');source.write_text(json.dumps([old]))
            stock_basis.migrate(path,source)
            stock_basis.save_many([dict(self.sample(),priceUsd=None,totalCost=18000)],path)
            stock_basis.migrate(path,source)
            self.assertEqual(stock_basis.get('RRSP','TEST',path=path)['totalCost'],18000)

    def test_missing_basis_does_not_fall_back_to_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db.sqlite3';stock_basis.save_many([],path)
            with self.assertRaises(ValueError):stock_basis.get('RRSP','MISSING',path=path)
