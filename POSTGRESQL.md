# PostgreSQL deployment

Docker Compose runs the application and PostgreSQL 17 in separate containers.
The database is accessible only on the Compose network, with its data in the
`postgres_data` named volume. Never use `docker compose down -v` on live data.
On EC2 the volume resides on the instance's EBS disk and survives stopping EC2.

Set a random URL-safe `POSTGRES_PASSWORD` in the untracked `.env` file (permissions
0600). Compose requires it; do not commit or print credentials. Changing this
variable after database initialization does not change the database password.

## Migrate existing records

Stop all other writers, including any standalone worksheet server. Keep a backup
of `data/fx-samples.sqlite3`. From the repository root:

```sh
docker compose build api
docker compose up -d db
docker compose stop api
docker compose run --rm --no-deps api python migrate_postgres.py
docker compose up -d api
```

Migration opens SQLite read-only, copies all five supported tables in one target
transaction, verifies every field and ID, and resets generated ID sequences.
An identical target is a safe no-op; a nonempty differing target is rejected.
Source data is retained. No external market or OpenAI requests are made.
If migration fails, do not start the new application until resolved. The old
SQLite file is a rollback snapshot, not a synchronized secondary database.

## Runtime and training

Compose sets `DATABASE_URL`; failures never fall back to SQLite. For host Python
execution set `DATABASE_URL` securely to a reachable PostgreSQL connection URI.
Without it, legacy SQLite mode remains available for fixtures and rollback.
Explicit non-default SQLite paths select fixture/export databases independently.
The FX training loader uses the configured database read-only; an explicit SQLite
input still supports archived datasets. `schema_diagram.py` remains a legacy
SQLite inspection utility.

One application worker remains required because broker-token coordination is
still in-process. PostgreSQL does not remove that restriction.

## Backups

Create a protected logical backup without putting credentials on the command line:

```sh
mkdir -p data/backups
chmod 700 data/backups
docker compose exec -T db pg_dump -U aimoney -d aimoney -Fc > data/backups/aimoney.dump
```

Use unique filenames and copy backups off the instance. Test restoring to a
separate database using `pg_restore` before relying on backups. Dump files contain
private financial records. EBS snapshots supplement logical backups.

Run the public and FastAPI checks normally. PostgreSQL integration checks require
`TEST_DATABASE_URL` pointing to a disposable database: they delete its test tables.
