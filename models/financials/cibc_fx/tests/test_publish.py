from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import publish_huggingface as hf


class PublishTests(unittest.TestCase):
    def test_public_destination_stops_before_upload(self):
        files={name:b'test' for name in hf.FILES}
        with patch.object(hf,'request',side_effect=[{'name':'test-user'},{'private':False}]) as request:
            with self.assertRaises(ValueError):hf.publish('test-token',files)
            self.assertEqual(request.call_count,2)

    def test_only_explicit_payload_is_accepted(self):
        with patch.object(hf,'request') as request:
            with self.assertRaises(ValueError):hf.publish('test-token',{'transactions.sqlite3':b'private'})
            request.assert_not_called()

    def test_invalid_name_does_not_make_network_request(self):
        with patch.object(hf,'request') as request:
            with self.assertRaises(ValueError):hf.publish('test-token',{},'../other')
            request.assert_not_called()
