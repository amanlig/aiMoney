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
    def test_edit_corrects_total_without_adding_sale(self):
        row=premiums.save_usd(dict(self.data,price_usd=29825),self.path)
        updated=premiums.save_usd(dict(self.data,price_usd=29.825),self.path,record_id=row['id'])
        self.assertEqual(updated['gross_usd'],14912.5)
        self.assertEqual(updated['id'],row['id'])
        self.assertEqual(updated['created_at'],row['created_at'])
        self.assertEqual(len(premiums.usd_records(self.path)),1)
        with self.assertRaises(ValueError):
            premiums.save_usd(dict(self.data,reviewed=False),self.path,record_id=row['id'])
        with self.assertRaisesRegex(ValueError,'not found'):
            premiums.save_usd(dict(self.data,settlement_date='2025-10-07'),self.path,record_id=999)
        other=premiums.save_usd(dict(self.data,settlement_date='2025-10-07'),self.path)
        with self.assertRaisesRegex(ValueError,'already recorded'):
            premiums.save_usd(dict(self.data,settlement_date='2025-10-07'),self.path,record_id=row['id'])
        self.assertEqual(premiums.usd_records(self.path)[1]['price_usd'],29.825)

    def test_edit_converted_reconciles_and_preserves_record(self):
        data=dict(self.data,fees_usd=0,fx=1.4,net_cad=29764)
        row=premiums.save(data,self.path)
        with self.assertRaisesRegex(ValueError,'reconcile'):
            premiums.save(dict(data,price_usd=40),self.path,record_id=row['id'])
        updated=premiums.save(dict(data,price_usd=40,net_cad=28000),self.path,record_id=row['id'])
        self.assertEqual(updated['net_usd'],20000)
        self.assertEqual(updated['created_at'],row['created_at'])
        self.assertEqual(len(premiums.records(self.path)),1)

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
