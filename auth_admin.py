"""Explicit authentication migration and manual user provisioning; no public signup."""
import argparse
import time

from authentication import initialize, normalize_email
from database import connect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--migrate', action='store_true')
    parser.add_argument('--add-user')
    parser.add_argument('--disable-user')
    parser.add_argument('--enable-user')
    parser.add_argument('--revoke-sessions')
    parser.add_argument('--list-users', action='store_true')
    args = parser.parse_args()
    with connect() as db:
        if not db.postgres:
            raise SystemExit('Configure DATABASE_URL for PostgreSQL before managing users.')
        db.execute('SELECT pg_advisory_xact_lock(72498124)')
        if args.migrate:
            initialize(db)
        if args.add_user:
            db.execute('INSERT INTO app_users(email,active,created_at) VALUES (?,1,?) ON CONFLICT(email) DO NOTHING',
                       (normalize_email(args.add_user), int(time.time())))
        for email, active in ((args.disable_user, 0), (args.enable_user, 1)):
            if email:
                db.execute('UPDATE app_users SET active=? WHERE email=?', (active, normalize_email(email)))
        for email in (args.disable_user, args.revoke_sessions):
            if email:
                db.execute('DELETE FROM auth_sessions WHERE user_id IN (SELECT id FROM app_users WHERE email=?)',
                           (normalize_email(email),))
                db.execute('DELETE FROM auth_challenges WHERE user_id IN (SELECT id FROM app_users WHERE email=?)',
                           (normalize_email(email),))
        if args.list_users:
            for row in db.execute('SELECT email,active FROM app_users ORDER BY email'):
                print(row['email'], 'active' if row['active'] else 'disabled')


if __name__ == '__main__':
    main()
