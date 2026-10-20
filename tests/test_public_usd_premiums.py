import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import option_premiums as premiums

class USDPremiumTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'test.sqlite3'
        self.data=dict(account='RRSP',symbol='ASTS',expiry='2028-01-21',strike=40,contracts=5,settlement_date='2025-10-06',price_usd=42.52,reviewed=True)
    def test_persistence_and_duplicate(self):
        row=premiums.save_usd(self.data,self.path)
        self.assertEqual(row['gross_usd'],21260)
        self.assertEqual(len(premiums.usd_records(self.path)),1)
        with self.assertRaisesRegex(ValueError,'already recorded'):premiums.save_usd(self.data,self.path)
    def test_review_and_numbers_required(self):
        for patch in [dict(reviewed=False),dict(contracts=1.5),dict(price_usd=float('nan')),dict(strike=-1),dict(settlement_date='2099-01-01')]:
            with self.subTest(patch=patch):
                with self.assertRaises(ValueError):premiums.save_usd(dict(self.data,**patch),self.path)
    def test_legacy_duplicates_in_both_directions(self):
        legacy=dict(self.data,fees_usd=0,fx=1.4,net_cad=29764)
        premiums.save(legacy,self.path)
        with self.assertRaisesRegex(ValueError,'already recorded'):premiums.save_usd(self.data,self.path)
        other=dict(self.data,settlement_date='2025-10-07')
        premiums.save_usd(other,self.path)
        with self.assertRaisesRegex(ValueError,'already recorded'):premiums.save(dict(legacy,settlement_date='2025-10-07'),self.path)

if __name__=='__main__':unittest.main()
