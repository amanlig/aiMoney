"""Copy legacy SQLite into PostgreSQL atomically; never changes source records."""
import argparse
import os
from pathlib import Path
import sqlite3
from database import DB, connect
from database_schema import STATEMENTS

TABLES = ('samples', 'stock_cost_basis', 'option_premiums',
          'option_premium_sales_usd', 'option_rollovers', 'closed_holdings', 'covered_positions', 'covered_position_rollovers', 'option_expirations', 'position_share_sources', 'deleted_position_sources', 'deleted_share_sources', 'recommendation_runs')


def initialize(db):
    for statement in STATEMENTS:
        db.execute(statement)


def migrate(source=DB, url=None):
    url = url or os.environ.get('DATABASE_URL')
    if not url:
        raise ValueError('Set DATABASE_URL to the target PostgreSQL database.')
    # Materialize a consistent read transaction before touching the target.
    with sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True) as legacy:
        legacy.row_factory = sqlite3.Row
        legacy.execute('BEGIN')
        names = {r['name'] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if names - set(TABLES):
            raise ValueError('Unknown source tables; review schema before migration.')
        snapshot = {table: [dict(r) for r in legacy.execute(f'SELECT * FROM {table} ORDER BY '+('source_key' if table=='deleted_position_sources' else 'id'))]
                    if table in names else [] for table in TABLES}
    with connect(url=url) as db:
        db.execute("SELECT pg_advisory_xact_lock(72498123)")
        initialize(db)
        db.execute('LOCK TABLE ' + ','.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE')
        existing = {table: [dict(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY '+('source_key' if table=='deleted_position_sources' else 'id'))] for table in TABLES}
        if any(existing.values()):
            if existing == snapshot:
                return {table: len(rows) for table, rows in snapshot.items()}
            raise ValueError('Target is not empty and differs from SQLite; nothing copied.')
        for table, rows in snapshot.items():
            for row in rows:
                # Identifiers come only from the known application schema.
                columns = ','.join('"' + key.replace('"', '""') + '"' for key in row)
                db.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join("?" for _ in row)})', tuple(row.values()))
            copied = [dict(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY '+('source_key' if table=='deleted_position_sources' else 'id'))]
            if copied != rows:
                raise ValueError(f'Verification failed for {table}; transaction rolled back.')
            if table not in {'covered_positions','covered_position_rollovers','option_expirations','position_share_sources','deleted_position_sources','deleted_share_sources'}:
                db.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id),1), COUNT(*)>0) FROM {table}")
    return {table: len(rows) for table, rows in snapshot.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DB)
    args = parser.parse_args()
    try:
        for table, count in migrate(args.source).items():
            print(f'{table}: {count} rows verified')
    except Exception:
        # Driver errors may contain connection details or financial values.
        raise SystemExit('Migration failed; no source records changed. Check connectivity and target schema/data.') from None
