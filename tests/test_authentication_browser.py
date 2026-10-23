"""Real HTTPS browser sign-in against synthetic users and a fake mail sender."""
import functools
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import uvicorn
import authentication as auth
from database import connect
from dashboard_server import create_app


class EmailSignInBrowserTests(unittest.TestCase):
    def test_email_code_remember_signout_and_disabled_account(self):
        from playwright.sync_api import sync_playwright, expect
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            connection = functools.partial(connect, root / 'auth.sqlite3')
            now = [1_800_000_000]
            messages = []
            service = auth.Authentication(connection=connection, secret='x' * 64,
                sender=lambda email, code: messages.append((email, code)), clock=lambda: now[0])
            with connection() as db:
                auth.initialize(db)
                db.execute('INSERT INTO app_users(email,active,created_at) VALUES (?,1,?)', ('owner@example.com', now[0]))
            key, cert = root / 'key.pem', root / 'cert.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost'],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            sock = socket.socket(); sock.bind(('127.0.0.1', 0))
            base = f'https://127.0.0.1:{sock.getsockname()[1]}'
            with patch.dict(os.environ, {'APP_ALLOWED_ORIGINS': base, 'AUTH_TRUST_PROXY': '0'}), \
                 patch('exit_optimizer.holdings', return_value=[]):
                app = create_app(refresh_macro=False, auth_enabled=True, auth_service=service)
                server = uvicorn.Server(uvicorn.Config(app, log_level='error', ssl_keyfile=str(key), ssl_certfile=str(cert)))
                worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
                worker.start()
                deadline = time.monotonic() + 10
                while not server.started:
                    if time.monotonic() > deadline: raise RuntimeError('Test HTTPS server did not start')
                    time.sleep(.01)
                try:
                    with sync_playwright() as playwright:
                        chrome = os.environ.get('CHROME_PATH') or shutil.which('chromium')
                        browser = playwright.chromium.launch(**({'executable_path': chrome} if chrome else {}), headless=True)
                        context = browser.new_context(ignore_https_errors=True, viewport={'width': 1440, 'height': 1000})
                        page = context.new_page(); errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(base + '/covered-call-optimizer')
                        expect(page.get_by_role('heading', name='Sign in', exact=True)).to_be_visible()
                        for viewport in ({'width': 390, 'height': 844}, {'width': 1440, 'height': 1000}):
                            page.set_viewport_size(viewport)
                            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                        page.get_by_label('Email address').fill('owner@example.com')
                        page.get_by_role('button', name='Send sign-in code').click()
                        expect(page.get_by_label('Sign-in code', exact=True)).to_be_visible()
                        deadline = time.monotonic() + 5
                        while not messages:
                            if time.monotonic() > deadline: raise RuntimeError('Fake mail was not sent')
                            time.sleep(.01)
                        code = messages[-1][1]
                        page.get_by_label('Sign-in code', exact=True).fill('11111111' if code != '11111111' else '22222222')
                        page.get_by_role('button', name='Verify & sign in').click()
                        expect(page.get_by_role('status')).to_contain_text('Invalid or expired code')
                        page.get_by_label('Sign-in code', exact=True).fill(code)
                        page.get_by_label('Remember this device for 30 days').check()
                        page.get_by_role('button', name='Verify & sign in').click()
                        expect(page.get_by_role('button', name='Sign out', exact=True)).to_be_visible()
                        cookie = next(c for c in context.cookies() if c['name'] == auth.COOKIE)
                        self.assertTrue(cookie['secure']); self.assertTrue(cookie['httpOnly'])
                        self.assertEqual(cookie['sameSite'], 'Lax'); self.assertGreater(cookie['expires'], 0)
                        page.reload()
                        expect(page.get_by_role('button', name='Sign out', exact=True)).to_be_visible()
                        page.get_by_role('button', name='Sign out', exact=True).click()
                        expect(page.get_by_role('heading', name='Sign in', exact=True)).to_be_visible()
                        self.assertEqual(context.request.get(base + '/api/profile/holdings').status, 401)
                        now[0] += 61
                        page.get_by_label('Email address').fill('owner@example.com')
                        page.get_by_role('button', name='Send sign-in code').click()
                        expect(page.get_by_label('Sign-in code', exact=True)).to_be_visible()
                        deadline = time.monotonic() + 5
                        while len(messages) < 2:
                            if time.monotonic() > deadline: raise RuntimeError('Second fake mail was not sent')
                            time.sleep(.01)
                        page.get_by_label('Sign-in code', exact=True).fill(messages[-1][1])
                        page.get_by_role('button', name='Verify & sign in').click()
                        expect(page.get_by_role('button', name='Sign out', exact=True)).to_be_visible()
                        with connection() as db:
                            db.execute('UPDATE app_users SET active=0')
                        page.reload()
                        expect(page.get_by_role('heading', name='Sign in', exact=True)).to_be_visible()
                        self.assertEqual(errors, [])
                        context.close(); browser.close()
                finally:
                    server.should_exit = True; worker.join(timeout=10); sock.close()


if __name__ == '__main__':
    unittest.main()
