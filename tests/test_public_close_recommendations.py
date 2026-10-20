import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import close_recommendations as rec
import stock_basis


class RecommendationTests(unittest.TestCase):
    def test_missing_key_does_not_call_api(self):
        with patch.object(rec,'configuration',return_value=(None,'test-model')),patch.object(rec.urllib.request,'urlopen') as api:
            with self.assertRaises(rec.ConfigurationError):rec.generate({})
            api.assert_not_called()

    def test_success_is_saved_and_replayable_without_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'test.sqlite3'
            captured={'created_at':'2026-10-16T00:00:00+00:00','calculations':{'closing_cash_cad':100}}
            response={'status':'completed','model':'test-model-version','id':'response-test','usage':{'total_tokens':10},'output':[{'type':'message','content':[{'type':'output_text','text':'Conditional assessment.'}]}]}
            with patch.object(rec,'DB',db),patch.object(rec,'configuration',return_value=('test-secret','test-model')),patch.object(rec,'snapshot',return_value=captured),patch.object(rec.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as api:
                result=rec.generate({'goal':'compare'})
                runs=rec.history()
                self.assertEqual(result['assessment'],'Conditional assessment.')
                self.assertEqual(len(runs),1)
                self.assertEqual(json.loads(runs[0]['snapshot_json']),captured)
                self.assertNotIn('test-secret',json.dumps(runs))
                body=json.loads(api.call_args.args[0].data)
                self.assertFalse(body['store'])
                self.assertNotIn('test-secret',json.dumps(body))
                self.assertEqual(body['input'],json.dumps(captured))

    def test_incomplete_api_result_is_not_saved(self):
        with patch.object(rec,'configuration',return_value=('test','test-model')),patch.object(rec,'snapshot',return_value={}),patch.object(rec.urllib.request,'urlopen',return_value=io.BytesIO(b'{"status":"incomplete"}')),patch.object(rec,'connect') as connect:
            with self.assertRaises(rec.AssessmentError):rec.generate({})
            connect.assert_not_called()

    def test_server_recalculates_from_confirmed_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);here=root/'models/financials/cibc_fx';(here/'artifacts').mkdir(parents=True);(root/'coveredCallOptimizer/data').mkdir(parents=True)
            dbpath=root/'coveredCallOptimizer/data/samples.sqlite3'
            with sqlite3.connect(dbpath) as db:
                db.execute('CREATE TABLE option_premiums (account,symbol,expiry,strike,contracts,net_cad)')
                db.execute("INSERT INTO option_premiums VALUES ('RRSP','ASTS','2028-01-21',40,5,29185.07)")
            stock_basis.save_many([{'account':'RRSP','currency':'CAD','symbol':'ASTS','quantity':500,'totalCost':17408.05}],dbpath)
            model={'method':'test','trained_at':'2026-01-01','samples':55,'settlement_end':'2025-11-03','data_sha256':'test','parameters':{d:{'adjustment':a,'usd_min':1,'usd_max':50000} for d,a in [('buy_usd',.016056538286390643),('sell_usd',-.015652361933521264)]}}
            (here/'artifacts/model.json').write_text(json.dumps(model))
            request=dict(goal='free_cash',bid=41.37,ask=16.7,reference=1.4159,stock_fees=0,call_fees=0,treatment='separate',closing_cash_cad=999999)
            quotes={'stock':{'bidPrice':41.37},'option':{'askPrice':16.7},'reference':1.4159}
            with patch.object(rec,'ROOT',root),patch.object(rec,'MODEL_DIR',here),patch.object(rec,'DB',dbpath):
                result=rec.snapshot(request,quotes)
                self.assertEqual(result['calculations']['closing_cash_cad'],16816.87)
                self.assertEqual(result['calculations']['total_gain_cad'],28593.89)
                for change in [{'bid':float('nan')},{'goal':'unknown'},{'stock_fees':-1}]:
                    with self.assertRaises(ValueError):rec.snapshot(dict(request,**change),quotes)


if __name__=='__main__':unittest.main()
