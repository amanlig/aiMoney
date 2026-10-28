from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import covered_positions as positions
from database import connect


class RealizedCarryTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/'carry.sqlite3'
        self.pool={('RRSP','RKLB'):1000}
        raw=dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2026-09-18',call_strike_native_currency=20)
        self.parent=positions.synchronize([raw],self.path)[0]
        positions.save_opening(self.parent['position_id'],dict(expiry='2026-09-18',strike=20,contracts=10,settlement_date='2026-08-01',price_usd=3,reviewed=True),path=self.path)
        positions.expire_worthless(self.parent['position_id'],dict(fees_usd=0,reviewed=True,position_revision=self.parent['position_revision']),self.path,today=date(2026,10,27))

    def create(self,shares,contracts,strike,expiry='2028-01-21'):
        with patch.object(positions,'date',wraps=date) as clock:
            clock.today.return_value=date(2026,10,1)
            return positions.create(dict(account='RRSP',symbol='RKLB',shares=shares,contracts=contracts,strike=strike,expiry=expiry),self.pool,path=self.path)

    def realized(self,h): return positions.prior_realized(h['position_id'],self.path)['prior_realized_option_usd']

    def test_split_retained_shares_split_realized_pl_not_duplicate_it(self):
        first=self.create(500,5,20)
        second=self.create(500,5,25)
        self.assertEqual(self.realized(first),1500)
        self.assertEqual(self.realized(second),1500)
        self.assertEqual(self.realized(first)+self.realized(second),3000)
        self.assertEqual(positions.expirations(self.path)[0]['realized_option_pl_usd'],3000)

    def test_next_expiry_cycle_carries_ancestors_once(self):
        first=self.create(1000,10,25,'2026-10-23')
        positions.save_opening(first['position_id'],dict(expiry='2026-10-23',strike=25,contracts=10,settlement_date='2026-10-01',price_usd=2,reviewed=True),path=self.path)
        positions.expire_worthless(first['position_id'],dict(fees_usd=0,reviewed=True,position_revision=first['position_revision']),self.path,today=date(2026,10,27))
        second=self.create(1000,10,30)
        carried=positions.prior_realized(second['position_id'],self.path)
        self.assertEqual(carried['prior_realized_option_usd'],5000)
        self.assertEqual(len(carried['realized_sources']),2)
        self.assertEqual(sorted(r['realized_option_pl_usd'] for r in positions.expirations(self.path)),[2000,3000])

    def test_merge_branches_keeps_parent_fraction_total_one(self):
        children=[self.create(500,5,strike,'2026-10-23') for strike in [25,30]]
        for child in children:
            positions.save_opening(child['position_id'],dict(expiry='2026-10-23',strike=child['call_strike_native_currency'],contracts=5,settlement_date='2026-10-01',price_usd=1,reviewed=True),path=self.path)
            positions.expire_worthless(child['position_id'],dict(fees_usd=0,reviewed=True,position_revision=child['position_revision']),self.path,today=date(2026,10,27))
        combined=self.create(1000,10,35)
        result=positions.prior_realized(combined['position_id'],self.path)
        self.assertEqual(result['prior_realized_option_usd'],4000)
        parent=next(r for r in result['realized_sources'] if r['position_id']==self.parent['position_id'])
        self.assertEqual(parent['fraction'],1)
        self.assertEqual(parent['realized_pl_usd'],3000)

    def test_resize_releases_and_reassigns_realized_share_fractions(self):
        first=self.create(1000,5,25)
        positions.allocate(first['position_id'],500,self.pool,self.path)
        second=self.create(500,5,30)
        self.assertEqual(self.realized(first),1500)
        self.assertEqual(self.realized(second),1500)

    def test_unrelated_account_or_preexisting_position_does_not_inherit(self):
        other=positions.create(dict(account='TFSA',symbol='RKLB',shares=1000,contracts=10,strike=20,expiry='2028-01-21'),{('TFSA','RKLB'):1000},path=self.path)
        self.assertEqual(self.realized(other),0)
        old=Path(self.path.parent)/'unrelated.sqlite3'
        raw=dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2026-09-18',call_strike_native_currency=20)
        first=positions.synchronize([raw],old)[0]
        sibling=positions.create(dict(account='RRSP',symbol='RKLB',shares=1000,contracts=10,strike=25,expiry='2028-01-21'),{('RRSP','RKLB'):2000},path=old)
        positions.save_opening(first['position_id'],dict(expiry='2026-09-18',strike=20,contracts=10,settlement_date='2026-08-01',price_usd=3,reviewed=True),path=old)
        positions.expire_worthless(first['position_id'],dict(fees_usd=0,reviewed=True,position_revision=first['position_revision']),old,today=date(2026,10,27))
        self.assertEqual(positions.prior_realized(sibling['position_id'],old)['prior_realized_option_usd'],0)

    def test_missing_realized_history_remains_unknown(self):
        with connect(self.path) as db: db.execute('UPDATE option_expirations SET realized_option_pl_usd=NULL WHERE id=?',(self.parent['position_id'],))
        child=self.create(1000,10,25)
        self.assertIsNone(self.realized(child))

    def test_backfill_existing_child_is_chronological_and_idempotent(self):
        child=self.create(1000,10,25)
        with connect(self.path) as db: db.execute('DELETE FROM position_share_sources')
        positions.synchronize([],self.path)
        self.assertEqual(self.realized(child),3000)
        positions.synchronize([],self.path)
        self.assertEqual(self.realized(child),3000)

    def test_partial_positions_do_not_duplicate_a_rounding_cent(self):
        with connect(self.path) as db: db.execute('UPDATE option_expirations SET realized_option_pl_usd=3000.01 WHERE id=?',(self.parent['position_id'],))
        first=self.create(500,5,20);second=self.create(500,5,25)
        self.assertEqual(self.realized(first),1500.01)
        self.assertEqual(self.realized(second),1500)
        self.assertEqual(self.realized(first)+self.realized(second),3000.01)

    def test_partial_positions_preserve_realized_losses(self):
        with connect(self.path) as db: db.execute('UPDATE option_expirations SET realized_option_pl_usd=-3000.01 WHERE id=?',(self.parent['position_id'],))
        first=self.create(500,5,20);second=self.create(500,5,25)
        self.assertEqual(self.realized(first),-1500.01)
        self.assertEqual(self.realized(second),-1500)
        self.assertEqual(self.realized(first)+self.realized(second),-3000.01)
