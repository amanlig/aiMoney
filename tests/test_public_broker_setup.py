import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
import questrade_quotes as quotes
import setup_questrade_local as setup
import exit_optimizer as optimizer


class LocalBrokerTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name);self.path=self.root/'.secrets/local-preview/questrade.json'

    def save(self):
        with patch.object(setup,'ROOT',self.root):setup.save_token('local-manual-test-token',self.path)

    def test_hidden_setup_is_private_and_does_not_overwrite_shared_copy(self):
        shared=self.root/'.secrets/questrade.json';shared.parent.mkdir()
        shared.write_text(json.dumps({'refresh_token':'cloud-test-token'}));before=shared.read_bytes()
        self.save()
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777,0o700)
        self.assertEqual(shared.read_bytes(),before)
        self.assertEqual(quotes.saved_refresh_token(self.path),'local-manual-test-token')
        with patch.object(setup,'ROOT',self.root),self.assertRaisesRegex(ValueError,'shared authorization'):
            setup.save_token('cloud-test-token',self.path)
        self.assertEqual(shared.read_bytes(),before)

    def test_missing_file_never_prompts_or_contacts_broker_in_web_worker(self):
        with patch.object(quotes.sys.stdin,'isatty',return_value=False),patch.object(quotes.getpass,'getpass') as prompt,patch.object(quotes,'fetch') as network:
            with self.assertRaisesRegex(quotes.BrokerNotConfigured,'not configured'):
                quotes.authorize(self.path)
        prompt.assert_not_called();network.assert_not_called()

    def test_bad_or_public_file_returns_safe_configuration_error(self):
        self.save();self.path.write_text('{"refresh_token":"never-print-token"')
        with self.assertRaises(quotes.BrokerNotConfigured) as error:quotes.saved_refresh_token(self.path)
        self.assertNotIn('never-print-token',str(error.exception))
        self.save();self.path.chmod(0o644)
        with self.assertRaisesRegex(quotes.BrokerNotConfigured,'private'):quotes.saved_refresh_token(self.path)

    def test_refresh_rotation_writes_only_local_file(self):
        self.save()
        response=dict(refresh_token='rotated-local-test-token',access_token='test-access',api_server='https://api01.iq.questrade.com/')
        with patch.object(quotes,'fetch',return_value=response):base,access=quotes.authorize(self.path)
        self.assertEqual(base,'https://api01.iq.questrade.com/v1/')
        self.assertEqual(access,'test-access')
        self.assertEqual(quotes.saved_refresh_token(self.path),'rotated-local-test-token')
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)

    def test_run_fails_before_any_history_or_broker_network_if_unconfigured(self):
        with patch.object(optimizer,'ROOT',self.root),patch.object(optimizer,'select_holding',return_value={}),patch.object(optimizer,'purchase_price',return_value=20),patch.object(optimizer,'public_fetch') as history,patch.object(optimizer,'authorize') as broker:
            with self.assertRaises(quotes.BrokerNotConfigured):optimizer.run(dict(account='RRSP',symbol='TEST'))
        history.assert_not_called();broker.assert_not_called()

    def test_history_failure_is_not_mislabeled_as_questrade_failure(self):
        path=self.root/'.secrets/questrade.json';path.parent.mkdir();path.write_text(json.dumps({'refresh_token':'local-test'}));path.chmod(0o600)
        with patch.object(optimizer,'ROOT',self.root),patch.object(optimizer,'select_holding',return_value={}),patch.object(optimizer,'purchase_price',return_value=20),patch.object(optimizer,'public_fetch',side_effect=URLError('network unavailable')),patch.object(optimizer,'authorize') as broker:
            with self.assertRaisesRegex(optimizer.StockHistoryUnavailable,'Yahoo Finance'):optimizer.run(dict(account='RRSP',symbol='TEST'))
        broker.assert_not_called()
