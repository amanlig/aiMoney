import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from option_premiums import save,records

class PremiumTests(unittest.TestCase):
    def test_persistence_reconciliation_and_duplicate(self):
        value=dict(account='RRSP',symbol='TEST',expiry='2028-01-21',strike=40,contracts=5,settlement_date='2025-10-06',price_usd=42.52,fees_usd=9.77,fx=1.3734,net_cad=29185.07,reviewed=True)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'samples.sqlite3'
            saved=save(value,path)
            self.assertEqual(saved['net_usd'],21250.23)
            self.assertEqual(records(path)[0]['net_cad'],29185.07)
            for changes in [{},{'net_cad':100},{'contracts':2.5},{'reviewed':False},{'fees_usd':-1}]:
                with self.assertRaises(ValueError):save(dict(value,**changes),path)
            self.assertEqual(len(records(path)),1)
