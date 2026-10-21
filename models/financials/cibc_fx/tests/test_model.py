import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model import fit,predict,split_dates,metrics


class ModelTests(unittest.TestCase):
    def rows(self):
        return [dict(direction=d,settlement_date=f'2025-01-{day:02d}',
                     yahoo_close=1.4,applied_rate=1.4*factor,
                     usd_amount=1000,cad_amount=1400*factor)
                for day in range(1,11)
                for d,factor in [('buy_usd',1.02),('sell_usd',.98)]]

    def test_recovers_known_adjustments(self):
        model=fit(self.rows())
        self.assertAlmostEqual(predict(model,'buy_usd',1.5,1000)['estimated_cad'],1530)
        self.assertAlmostEqual(predict(model,'sell_usd',1.5,1000)['estimated_cad'],1470)
        self.assertAlmostEqual(metrics(model,self.rows())['mean_absolute_cad_error'],0)

    def test_split_keeps_same_dates_together(self):
        train,test=split_dates(self.rows())
        self.assertLess(max(r['settlement_date'] for r in train),min(r['settlement_date'] for r in test))
        self.assertEqual(len(train)+len(test),20)
        changed=[dict(r,applied_rate=9) for r in test]
        self.assertEqual(fit(train),fit([r for r in train+changed if r['settlement_date'] < '2025-01-09']))

    def test_rejects_invalid_prediction_inputs(self):
        model=fit(self.rows())
        for direction,rate,amount in [('bad',1.4,1000),('buy_usd',0,1000),('sell_usd',float('nan'),1000),('buy_usd',1.4,-1)]:
            with self.assertRaises(ValueError):predict(model,direction,rate,amount)
        with self.assertRaises(ValueError):fit(self.rows()[:2])

    def test_outlier_does_not_dominate_median(self):
        rows=self.rows()
        rows[0]['applied_rate']=100
        self.assertAlmostEqual(fit(rows)['parameters']['buy_usd']['adjustment'],.02)
        self.assertTrue(predict(fit(rows),'buy_usd',1.4,2000)['outside_training_amount_range'])


if __name__=='__main__':unittest.main()
