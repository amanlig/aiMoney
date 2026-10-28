"""Offline tests for the explicit public package boundary; no credentials required."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('publisher',ROOT/'publish_huggingface.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


class PublishingTests(unittest.TestCase):
    def test_package_is_allowlisted_reproducible_and_model_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p,'PACKAGE',Path(tmp)):
            files=p.prepare()
            self.assertEqual(files,p.prepare())
        self.assertEqual(set(files),set(p.FILES))
        self.assertEqual(files['model.py'],(ROOT/'model.py').read_bytes())
        manifest=json.loads(files['manifest.json'])
        for name,digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(),digest)
        sample=json.loads(files['examples/sample_input.json'])
        self.assertEqual(sample['account'],'SYNTHETIC')
        self.assertEqual(sample['symbol'],'DEMO')
        result=json.loads(files['examples/expected_result.json'])
        self.assertEqual(result['excluded'],2)
        self.assertEqual(len(result['top_choices']),3)
        self.assertTrue(all('.secrets' not in name and 'reports/' not in name for name in files))

    def test_extra_upload_file_rejected_before_network(self):
        with patch.object(p,'request') as request:
            with self.assertRaises(ValueError):p.publish('unused',{'secret.txt':b'example'},'example')
            request.assert_not_called()

    def test_private_repository_is_not_made_public(self):
        files={name:b'example' for name in p.FILES}
        with patch.object(p,'request',side_effect=[{'name':'demo-user'},{'private':True}]) as request:
            with self.assertRaises(ValueError):p.publish('unused',files,'example')
            self.assertEqual(request.call_count,2)

    def test_unrelated_existing_repository_is_not_overwritten(self):
        files={name:b'example' for name in p.FILES}
        with patch.object(p,'request',side_effect=[{'name':'demo-user'},
             {'private':False,'siblings':[{'rfilename':'other_model.py'}]}]) as request:
            with self.assertRaises(ValueError):p.publish('unused',files,'example')
            self.assertEqual(request.call_count,2)

    def test_public_upload_and_remote_checksums(self):
        files={name:b'example' for name in p.FILES}
        calls=[]
        def fake(path,token,body=None,content_type='application/json',raw=False):
            calls.append((path,body))
            if path=='/api/whoami-v2':return {'name':'demo-user'}
            if path=='/api/models/demo-user/example':return {'private':False,'sha':'before','siblings':[]}
            if path.endswith('/commit/main'):
                operations=[json.loads(line) for line in body.splitlines()]
                self.assertEqual(operations[0]['value']['parentCommit'],'before')
                self.assertEqual({x['value']['path'] for x in operations[1:]},set(p.FILES))
                return {'commitOid':'new-commit'}
            if path.endswith('/revision/new-commit'):return {'private':False}
            if raw:return b'example'
            self.fail(path)
        with tempfile.TemporaryDirectory() as tmp, patch.object(p,'HERE',Path(tmp)),patch.object(p,'request',side_effect=fake):
            (Path(tmp)/'artifacts').mkdir()
            receipt=p.publish('unused',files,'example')
            self.assertTrue(receipt['verified'])
            self.assertFalse(receipt['private'])


if __name__=='__main__':unittest.main()
