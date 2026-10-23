"""Email-code authentication for manually provisioned, shared-portfolio users.

No registration endpoint. Apply the schema and add users with auth_admin.py.
Only code HMACs and session-token hashes are persisted in the database.
"""
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import time

from database import connect

COOKIE = '__Host-aimoney-session'
CODE_TTL = 600
MAX_ATTEMPTS = 5
SHORT_SESSION = 12 * 3600
REMEMBER_SESSION = 30 * 86400
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS app_users (
        id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE,
        active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
        created_at BIGINT NOT NULL,
        CHECK (email = lower(email)))""",
    """CREATE TABLE IF NOT EXISTS auth_challenges (
        id TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
        code_hash TEXT NOT NULL, created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, used_at BIGINT)""",
    """CREATE TABLE IF NOT EXISTS auth_sessions (
        token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
        created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS auth_rate_limits (
        bucket TEXT PRIMARY KEY, window_start BIGINT NOT NULL, hits INTEGER NOT NULL)""",
)


def normalize_email(value):
    email = value.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", email):
        raise ValueError('Enter a valid email address.')
    return email


def initialize(db):
    for statement in SCHEMA:
        db.execute(statement)
    db.execute('CREATE INDEX IF NOT EXISTS auth_challenges_user ON auth_challenges(user_id)')
    db.execute('CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions(user_id)')


def send_code(email, code):
    """Use the EC2 instance role, with no long-lived AWS credentials in the app."""
    import boto3
    from botocore.config import Config
    client = boto3.client('sesv2', region_name=os.environ.get('AWS_REGION', 'us-west-2'),
                          config=Config(connect_timeout=5, read_timeout=10,
                                        retries={'max_attempts': 2, 'mode': 'standard'}))
    client.send_email(
        FromEmailAddress=os.environ['AUTH_EMAIL_FROM'],
        Destination={'ToAddresses': [email]},
        Content={'Simple': {
            'Subject': {'Data': 'Your aiMoney sign-in code', 'Charset': 'UTF-8'},
            'Body': {'Text': {'Data': f'Your aiMoney sign-in code is: {code}\n\n'
                'It expires in 10 minutes and can be used once.\n'
                'If you did not request this, ignore this email. Do not share the code.',
                'Charset': 'UTF-8'}}}})


class RateLimited(Exception):
    pass


class Authentication:
    def __init__(self, *, connection=connect, secret=None, sender=send_code, clock=time.time):
        self.connection, self.sender, self.clock = connection, sender, clock
        if secret is None:
            if not os.environ.get('AUTH_EMAIL_FROM'):
                raise RuntimeError('Configure a verified AUTH_EMAIL_FROM before enabling authentication.')
            path = Path(os.environ.get('AUTH_SECRET_FILE', Path(__file__).parent / '.secrets/auth.json'))
            if path.stat().st_mode & 0o077:
                raise RuntimeError('Authentication secret must have owner-only permissions.')
            secret = json.loads(path.read_text())['secret']
        if not isinstance(secret, str) or len(secret) < 64:
            raise RuntimeError('Authentication requires a random secret of at least 64 characters.')
        self.secret = secret.encode()

    def lock(self, db):
        if db.postgres:
            db.execute('SELECT pg_advisory_xact_lock(72498124)')
        else:
            db.execute('BEGIN IMMEDIATE')

    def digest(self, text):
        return hmac.new(self.secret, text.encode(), hashlib.sha256).hexdigest()

    def limit(self, db, bucket, window, maximum, now):
        key = self.digest(bucket)
        row = db.execute('SELECT window_start,hits FROM auth_rate_limits WHERE bucket=?', (key,)).fetchone()
        if row is not None and row['window_start'] > now - window:
            if row['hits'] >= maximum:
                return False
            db.execute('UPDATE auth_rate_limits SET hits=hits+1 WHERE bucket=?', (key,))
        else:
            db.execute('INSERT INTO auth_rate_limits(bucket,window_start,hits) VALUES (?,?,1) '
                       'ON CONFLICT(bucket) DO UPDATE SET window_start=excluded.window_start,hits=1', (key, now))
        return True

    def request_code(self, email, ip):
        email = normalize_email(email)
        now = int(self.clock())
        challenge = secrets.token_urlsafe(24)
        delivery = None
        with self.connection() as db:
            self.lock(db)
            allowed = (self.limit(db, 'request-global', 3600, 200, now)
                       and self.limit(db, 'request-ip:' + ip, 3600, 20, now)
                       and self.limit(db, 'request-email-hour:' + email, 3600, 5, now)
                       and self.limit(db, 'request-email-minute:' + email, 60, 1, now))
            db.execute('DELETE FROM auth_challenges WHERE expires_at<?', (now,))
            db.execute('DELETE FROM auth_sessions WHERE expires_at<?', (now,))
            db.execute('DELETE FROM auth_rate_limits WHERE window_start<?', (now - 86400,))
            user = db.execute('SELECT id FROM app_users WHERE email=? AND active=1', (email,)).fetchone()
            if allowed and user:
                # Only the newest code for a user is valid, even across browsers.
                db.execute('DELETE FROM auth_challenges WHERE user_id=?', (user['id'],))
                code = f'{secrets.randbelow(100_000_000):08d}'
                db.execute('INSERT INTO auth_challenges(id,user_id,code_hash,created_at,expires_at) VALUES (?,?,?,?,?)',
                           (challenge, user['id'], self.digest(challenge + ':' + code), now, now + CODE_TTL))
                delivery = (email, code, challenge)
        if not allowed:
            raise RateLimited()
        # Unknown/inactive users get the same response and never receive mail.
        return challenge, delivery

    def deliver(self, email, code, challenge):
        try:
            self.sender(email, code)
        except Exception:
            # Neither provider payloads nor the email/code enter application logs.
            logging.getLogger(__name__).error('Sign-in email delivery failed.')
            with self.connection() as db:
                db.execute('DELETE FROM auth_challenges WHERE id=?', (challenge,))

    def verify(self, challenge, code, remember, ip):
        now = int(self.clock())
        result = None
        with self.connection() as db:
            self.lock(db)
            allowed = self.limit(db, 'verify-ip:' + ip, 900, 100, now)
            row = db.execute('SELECT c.*,u.email,u.active FROM auth_challenges c '
                             'JOIN app_users u ON u.id=c.user_id WHERE c.id=?', (challenge,)).fetchone()
            if allowed and row and row['active'] == 1 and row['used_at'] is None and row['expires_at'] > now and row['attempts'] < MAX_ATTEMPTS:
                db.execute('UPDATE auth_challenges SET attempts=attempts+1 WHERE id=?', (challenge,))
                if hmac.compare_digest(row['code_hash'], self.digest(challenge + ':' + code)):
                    token = secrets.token_urlsafe(32)
                    ttl = REMEMBER_SESSION if remember else SHORT_SESSION
                    db.execute('UPDATE auth_challenges SET used_at=? WHERE id=?', (now, challenge))
                    db.execute('INSERT INTO auth_sessions(token_hash,user_id,created_at,expires_at) VALUES (?,?,?,?)',
                               (hashlib.sha256(token.encode()).hexdigest(), row['user_id'], now, now + ttl))
                    result = (token, row['email'], ttl)
        # Failures commit the attempt counters before returning to the route.
        if not allowed:
            raise RateLimited()
        return result

    def session(self, token):
        if not token or len(token) > 128:
            return None
        with self.connection() as db:
            row = db.execute('SELECT u.id,u.email FROM auth_sessions s JOIN app_users u ON u.id=s.user_id '
                             'WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',
                             (hashlib.sha256(token.encode()).hexdigest(), int(self.clock()))).fetchone()
            return dict(row) if row else None

    def logout(self, token):
        if token:
            with self.connection() as db:
                db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
