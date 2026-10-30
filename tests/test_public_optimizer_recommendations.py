import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import optimizer_recommendations as rec
import optimizer_assessments as service


class Recommendations(unittest.TestCase):
    def test_server_snapshot_fixed_today_and_expire(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'reports').mkdir()
            inputs=dict(initial_purchase_price_usd=20,account='RRSP',symbol='TEST',shares=100,contracts=1,held={},captured_at='capture',stock={'bidPrice':20,'askPrice':21},interest_rate=dict(rate=.05,selection={'mode':'manual','annual_percent':5}))
            (root/'reports/exit-optimizer-rrsp-test.json').write_text(json.dumps({'inputs':inputs}))
            baseline={'rows':[{'strategy':'Close now','mean':100}]}
            expire={'exit_mode':'expire','option_profit_usd':5}
            analysis=dict(top_choices=[dict(expiry='2027-01-01',strike=40.0,expire_worthless=expire)],assumptions=[],version='test',search={},minimum_stock_sale_price_usd=22)
            request=dict(account='RRSP',symbol='TEST',goal='keep_exposure',captured_at='capture',stock_price=30,modes={'RRSP|TEST|2027-01-01|40':'expire'},close_today={'mean':99999})
            with patch.object(rec.optimizer,'ROOT',root),patch.object(rec.optimizer,'holdings',return_value=[inputs]),patch.object(rec.optimizer.model,'stock_price_scenario',return_value=inputs),patch.object(rec.optimizer.model,'evaluate',side_effect=[baseline,analysis]) as evaluate:
                result=rec.snapshot(request)
            self.assertEqual(result['close_today']['mean'],100)
            self.assertTrue(all(call.kwargs['rate']==.05 for call in evaluate.call_args_list))
            self.assertEqual(result['interest_rate']['rate'],.05)
            self.assertEqual(result['displayed_rollovers'],[expire])
            request['expected_rate']=.06
            with patch.object(rec.optimizer,'ROOT',root),patch.object(rec.optimizer,'holdings',return_value=[inputs]):
                with self.assertRaisesRegex(ValueError,'interest rate changed'):rec.snapshot(request)
            request.pop('expected_rate')
            request['captured_at']='stale'
            with patch.object(rec.optimizer,'ROOT',root),patch.object(rec.optimizer,'holdings',return_value=[inputs]):
                with self.assertRaisesRegex(ValueError,'Quotes changed'):rec.snapshot(request)

    def test_successful_assessment_saved_without_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            response=dict(status='completed',model='test',output=[dict(type='message',content=[dict(type='output_text',text='Assessment')])])
            with patch.object(service,'DB',Path(folder)/'db.sqlite3'),patch.object(service,'configuration',return_value=('secret-test','test')),patch.object(service.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as api:
                result=service.generate({'created_at':'now','currency':'USD'})
                runs=service.history()
            self.assertEqual(result['assessment'],'Assessment')
            self.assertEqual(len(runs),1)
            self.assertNotIn('secret-test',json.dumps(runs))
            self.assertFalse(json.loads(api.call_args.args[0].data)['store'])

    def test_incomplete_not_saved(self):
        with patch.object(service,'configuration',return_value=('test','test')),patch.object(service.urllib.request,'urlopen',return_value=io.BytesIO(b'{"status":"incomplete"}')),patch.object(service,'connect') as db:
            with self.assertRaises(service.AssessmentError):service.generate({})
            db.assert_not_called()

    def test_invalid_goal_rejected(self):
        with self.assertRaises(ValueError):rec.snapshot({'goal':'invented'})


if __name__=='__main__':unittest.main()
