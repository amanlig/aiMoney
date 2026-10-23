"""Authentication contracts with synthetic identities and a fake email sender."""
import functools
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import authentication as auth
from database import connect
import dashboard_server as server


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.connection = (functools.partial(connect, url=os.environ['TEST_AUTH_DATABASE_URL'])
                           if os.environ.get('TEST_AUTH_DATABASE_URL') else
                           functools.partial(connect, self.root / 'auth.sqlite3'))
        self.now = 1_800_000_000
        self.messages = []
        self.service = auth.Authentication(connection=self.connection, secret='s' * 64,
                                           sender=lambda email, code: self.messages.append((email, code)),
                                           clock=lambda: self.now)
        with self.connection() as db:
            auth.initialize(db)
            if db.postgres:
                # TEST_AUTH_DATABASE_URL must name a disposable test database.
                db.execute('TRUNCATE app_users,auth_challenges,auth_sessions,auth_rate_limits RESTART IDENTITY CASCADE')
            db.execute('INSERT INTO app_users(email,active,created_at) VALUES (?,1,?)', ('owner@example.com', self.now))
            db.execute('INSERT INTO app_users(email,active,created_at) VALUES (?,0,?)', ('disabled@example.com', self.now))

    def tearDown(self):
        self.temp.cleanup()

    def issue(self, email='owner@example.com', ip='test-ip'):
        challenge, delivery = self.service.request_code(email, ip)
        if delivery:
            self.service.deliver(*delivery)
        return challenge

    def login(self, remember=False):
        challenge = self.issue()
        return self.service.verify(challenge, self.messages[-1][1], remember, 'test-ip')

    def test_only_active_manually_created_users_receive_codes(self):
        for address in ('missing@example.com', 'disabled@example.com'):
            challenge = self.issue(address)
            self.assertIsNone(self.service.verify(challenge, '12345678', False, 'test-ip'))
        self.assertEqual(self.messages, [])
        self.issue('  OWNER@EXAMPLE.COM ')
        self.assertEqual(self.messages[0][0], 'owner@example.com')
        with self.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) AS n FROM app_users').fetchone()['n'], 2)

    def test_code_and_session_are_hashed_at_rest_and_code_is_single_use(self):
        challenge = self.issue()
        code = self.messages[-1][1]
        with self.connection() as db:
            row = db.execute('SELECT * FROM auth_challenges').fetchone()
            self.assertNotEqual(row['code_hash'], code)
        token, email, ttl = self.service.verify(challenge, code, False, 'test-ip')
        self.assertEqual(email, 'owner@example.com')
        self.assertEqual(ttl, auth.SHORT_SESSION)
        self.assertIsNone(self.service.verify(challenge, code, False, 'test-ip'))
        with self.connection() as db:
            row = db.execute('SELECT * FROM auth_sessions').fetchone()
            self.assertEqual(row['token_hash'], hashlib.sha256(token.encode()).hexdigest())
            self.assertNotEqual(row['token_hash'], token)

    def test_expired_code_and_new_code_invalidate_previous_code(self):
        challenge = self.issue(); code = self.messages[-1][1]
        self.now += auth.CODE_TTL
        self.assertIsNone(self.service.verify(challenge, code, False, 'test-ip'))
        current = self.issue()
        self.now += 61
        latest = self.issue()
        self.assertIsNone(self.service.verify(current, self.messages[-2][1], False, 'test-ip'))
        self.assertIsNotNone(self.service.verify(latest, self.messages[-1][1], False, 'test-ip'))

    def test_concurrent_verification_issues_exactly_one_session(self):
        challenge = self.issue(); code = self.messages[-1][1]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.service.verify(challenge, code, True, 'test-ip'), range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        with self.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) AS n FROM auth_sessions').fetchone()['n'], 1)

    def test_failed_attempts_commit_and_lock_out_even_correct_code(self):
        challenge = self.issue(); code = self.messages[-1][1]
        wrong = '11111111' if code != '11111111' else '22222222'
        for _ in range(auth.MAX_ATTEMPTS):
            self.assertIsNone(self.service.verify(challenge, wrong, False, 'test-ip'))
        self.assertIsNone(self.service.verify(challenge, code, False, 'test-ip'))
        with self.connection() as db:
            self.assertEqual(db.execute('SELECT attempts FROM auth_challenges').fetchone()['attempts'], auth.MAX_ATTEMPTS)

    def test_request_cooldown_hourly_and_ip_limits(self):
        self.issue()
        with self.assertRaises(auth.RateLimited):
            self.issue()
        for _ in range(3):
            self.now += 61; self.issue()
        self.now += 61
        with self.assertRaises(auth.RateLimited):
            self.issue()
        self.now += 3601
        self.issue()
        for index in range(19):
            self.issue(f'unknown{index}@example.com', 'other-ip')
        self.issue('last@example.com', 'other-ip')
        with self.assertRaises(auth.RateLimited):
            self.issue('blocked@example.com', 'other-ip')

    def test_remembered_session_expiry_revocation_and_disabled_user(self):
        token, _, ttl = self.login(remember=True)
        self.assertEqual(ttl, auth.REMEMBER_SESSION)
        self.assertIsNotNone(self.service.session(token))
        with self.connection() as db:
            db.execute('UPDATE app_users SET active=0 WHERE email=?', ('owner@example.com',))
        self.assertIsNone(self.service.session(token))
        with self.connection() as db:
            db.execute('UPDATE app_users SET active=1 WHERE email=?', ('owner@example.com',))
        self.service.logout(token)
        self.assertIsNone(self.service.session(token))
        self.now += 61
        token, _, _ = self.login()
        self.now += auth.SHORT_SESSION
        self.assertIsNone(self.service.session(token))

    def test_email_delivery_failure_invalidates_challenge_without_logging_code(self):
        challenge, delivery = self.service.request_code('owner@example.com', 'test-ip')
        self.service.sender = lambda *args: (_ for _ in ()).throw(RuntimeError('sensitive provider payload'))
        with self.assertLogs('authentication', level='ERROR') as logged:
            self.service.deliver(*delivery)
        self.assertNotIn('sensitive provider payload', ''.join(logged.output))
        self.assertNotIn(delivery[1], ''.join(logged.output))
        self.assertIsNone(self.service.verify(challenge, delivery[1], False, 'test-ip'))

    def test_missing_schema_prevents_authentication_enabled_startup(self):
        with self.connection() as db:
            db.execute('DROP TABLE auth_sessions')
        with self.assertRaises((sqlite3.Error, server.psycopg.Error)):
            with TestClient(server.create_app(refresh_macro=False, auth_enabled=True, auth_service=self.service)):
                self.fail('An incomplete authentication migration must not start.')

    def test_http_protection_cookie_csrf_logout_and_generic_responses(self):
        (self.root / 'frontend/dist').mkdir(parents=True)
        (self.root / 'frontend/dist/index.html').write_text('<div id="root"></div>')
        (self.root / 'reports').mkdir()
        with patch.object(server, 'ROOT', self.root), patch.dict(os.environ, {
                'APP_ALLOWED_ORIGINS': 'https://aimoney.test', 'AUTH_TRUST_PROXY': '0'}):
            with TestClient(server.create_app(refresh_macro=False, auth_enabled=True, auth_service=self.service),
                            base_url='https://aimoney.test') as client:
                for path in ('/api/profile/holdings', '/api/stock-cost-basis', '/openapi.json'):
                    self.assertEqual(client.get(path).status_code, 401)
                self.assertEqual(client.get('/covered-call-optimizer', follow_redirects=False).headers['location'], '/signin')
                self.assertEqual(client.get('/signin').status_code, 200)
                self.assertEqual(client.get('/api/health').status_code, 200)
                origin = {'Origin': 'https://aimoney.test'}
                self.assertEqual(client.post('/api/auth/request-code', json={'email': 'owner@example.com'}).status_code, 403)
                missing = client.post('/api/auth/request-code', json={'email': 'missing@example.com'}, headers=origin)
                known = client.post('/api/auth/request-code', json={'email': 'owner@example.com'}, headers=origin)
                self.assertEqual(missing.status_code, known.status_code)
                self.assertEqual(missing.json()['message'], known.json()['message'])
                self.assertNotIn(self.messages[-1][1], known.text)
                challenge = known.json()['challenge_id']
                response = client.post('/api/auth/verify', json={'challenge_id': challenge, 'code': self.messages[-1][1], 'remember': True}, headers=origin)
                self.assertEqual(response.status_code, 200)
                cookie = response.headers['set-cookie']
                for flag in ('Secure', 'HttpOnly', 'SameSite=lax', 'Path=/', f'Max-Age={auth.REMEMBER_SESSION}'):
                    self.assertIn(flag, cookie)
                self.assertNotIn('Domain=', cookie)
                self.assertEqual(client.get('/api/auth/session').json()['email'], 'owner@example.com')
                self.assertEqual(client.get('/openapi.json').status_code, 200)
                self.assertEqual(client.post('/api/auth/logout', json={}, headers={'Origin': 'https://evil.test'}).status_code, 403)
                self.assertEqual(client.post('/api/auth/logout', json={}, headers=origin).status_code, 200)
                self.assertEqual(client.get('/api/auth/session').status_code, 401)
                self.assertEqual(client.get('/api/stock-cost-basis').status_code, 401)
                self.now += 61
                fresh = client.post('/api/auth/request-code', json={'email': 'owner@example.com'}, headers=origin)
                response = client.post('/api/auth/verify', json={
                    'challenge_id': fresh.json()['challenge_id'], 'code': self.messages[-1][1], 'remember': False}, headers=origin)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('Max-Age=', response.headers['set-cookie'])


if __name__ == '__main__':
    unittest.main()
