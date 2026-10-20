import sys
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import close_simulator_server as serve


class RefreshTests(unittest.TestCase):
    def handler(self,origin='http://localhost:8766'):
        handler=serve.Handler.__new__(serve.Handler)
        handler.path='/api/quotes/refresh'
        handler.server=SimpleNamespace(server_port=8766)
        handler.headers={'Origin':origin}
        handler.send_json=Mock()
        return handler

    def test_other_origins_cannot_refresh(self):
        handler=self.handler('https://example.com')
        with patch.object(serve,'refreshed_quotes') as refresh:
            handler.do_POST()
        refresh.assert_not_called()
        self.assertEqual(handler.send_json.call_args.args[1],403)

    def test_refresh_success_returns_quotes(self):
        handler=self.handler()
        with patch.object(serve,'refreshed_quotes',return_value={'reference':1.4}) as refresh:
            handler.do_POST()
        refresh.assert_called_once()
        handler.send_json.assert_called_once_with({'reference':1.4})
        self.assertFalse(serve.REFRESH_LOCK.locked())

    def test_failure_is_reported_and_lock_released(self):
        handler=self.handler()
        with patch.object(serve,'refreshed_quotes',side_effect=ValueError('private error')):
            handler.do_POST()
        self.assertEqual(handler.send_json.call_args.args[1],502)
        self.assertNotIn('private error',str(handler.send_json.call_args))
        self.assertFalse(serve.REFRESH_LOCK.locked())

    def test_concurrent_refresh_is_rejected(self):
        handler=self.handler()
        serve.REFRESH_LOCK.acquire()
        try:
            with patch.object(serve,'refreshed_quotes') as refresh:handler.do_POST()
            refresh.assert_not_called()
            self.assertEqual(handler.send_json.call_args.args[1],409)
        finally:serve.REFRESH_LOCK.release()
