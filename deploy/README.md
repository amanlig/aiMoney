# AWS deployment and authorized users — us-west-2

Current host: `https://aimoney.kodekomplete.com`. One EC2 instance runs Caddy,
FastAPI/React and PostgreSQL. PostgreSQL and the app publish no host ports.
Only Caddy publishes 80/443; SSH is restricted to the operator's IP. EBS is encrypted.
See [architecture](../ARCHITECTURE.md) and [authentication flow](../docs/authentication.md).

## Email sign-in

The sign-in page replaces HTTP Basic Authentication. Only active emails manually
inserted in PostgreSQL `app_users` can sign in. There is no registration endpoint
or browser user-management page. All authorized users share the same portfolio
and controls; independent portfolios and roles are future work.

An authorized email receives an 8-digit, single-use code through Amazon SES.
Codes expire after ten minutes and five attempts. Sessions last 12 hours, or
30 days when the user selects “Remember this device.” Disable a user to block
existing sessions immediately; sign-out revokes the current server session.
Requests are limited per email/IP and globally. Unknown and inactive emails
receive the same HTTP response but no message.

On EC2, from `/home/ubuntu/aiMoney`, apply the additive migration and create a user:

```sh
docker compose --env-file .env.aws -f compose.aws.yaml run --rm --no-deps api \
  python auth_admin.py --migrate --add-user person@example.com
```

After the app is running:

```sh
docker compose --env-file .env.aws -f compose.aws.yaml exec -T api \
  python auth_admin.py --add-user person@example.com
docker compose --env-file .env.aws -f compose.aws.yaml exec -T api \
  python auth_admin.py --list-users
docker compose --env-file .env.aws -f compose.aws.yaml exec -T api \
  python auth_admin.py --disable-user person@example.com
docker compose --env-file .env.aws -f compose.aws.yaml exec -T api \
  python auth_admin.py --enable-user person@example.com
docker compose --env-file .env.aws -f compose.aws.yaml exec -T api \
  python auth_admin.py --revoke-sessions person@example.com
```

The operator can also use SQL against the private database. Store lowercase,
trimmed addresses and use `active=1` for enabled users:

```sql
INSERT INTO app_users (email, active, created_at)
VALUES ('person@example.com', 1, extract(epoch FROM now())::bigint);
UPDATE app_users SET active=0 WHERE email='person@example.com';
```

Use `--disable-user` when possible: it also deletes that user's sessions and
outstanding codes, so re-enabling cannot reactivate an old session.
No automatic owner account is created at application startup.

## Email and authentication configuration

- Verify the app subdomain in SES and publish its DKIM CNAME records in Route 53.
  Set `AUTH_EMAIL_FROM` to a sender under that identity. Production SES access
  is required for unverified recipients; the current us-west-2 account has it.
- Attach an EC2 instance role restricted to `ses:SendEmail` on that SES identity,
  with `ses:FromAddress` restricted to the configured address. The AWS SDK uses
  temporary role credentials; do not add AWS access keys to the app.
- Require IMDSv2 and set the response hop limit to 2 for container access.
- Store a cryptographically random 64-character (or longer) HMAC secret in
  `.secrets/auth.json` as `{"secret":"..."}`. Generate it on the server; never
  print it into logs. Directory permissions: `700`; secret file: `600`.
- `.env.aws` is owner-only (`600`) and contains the full hostname, runtime UID/GID,
  versioned app image, database password, and verified sender. `APP_AUTH_ENABLED=1`
  is set explicitly in the cloud Compose file. Caddy has no Basic Auth password.
- Only Caddy can reach the API externally. It overwrites `X-AiMoney-Client-IP`;
  the app trusts that header only when cloud proxy mode is enabled. Preserve
  this boundary when adding proxies or publishing additional ports.

Do not print `.env.aws`, auth secrets, one-time codes or session cookies. The
application stores code HMACs and hashed session tokens, never plaintext codes
or cookie tokens. The `__Host-` cookie is Secure, HttpOnly and SameSite=Lax.

## Fresh instance setup

Use an official Ubuntu Server LTS x86 image, `t3.medium`, and an encrypted 30 GiB
gp3 disk in a public subnet in us-west-2. Require IMDSv2. Allow 22 only from the
operator IP and 80/443 publicly. Never expose 8765 or 5432. Allocate an Elastic IP
and add the chosen A record without modifying unrelated records.

Install Docker Engine and Compose from the official Ubuntu repository:
https://docs.docker.com/engine/install/ubuntu/ . Enable Docker at boot. Clone the
repository and check out a reviewed commit. From the repository root:

```sh
mkdir -p data reports .secrets models/financials/cibc_fx/artifacts
chmod 700 .secrets
cp deploy/aws.env.example .env.aws
chmod 600 .env.aws
```

Configure the verified SES sender, role and auth secret above. Set UID/GID to
match the owner of the runtime folders. Generate a new URL-safe hexadecimal
PostgreSQL password. Do not log resolved Compose configuration.

## Data cutover and startup

Take a fresh logical PostgreSQL `pg_dump -Fc` backup. Transfer it, saved data and
captures, required Questrade/OpenAI configuration and optional model artifacts
through encrypted SSH to the intended server. These private files stay outside
Git and Docker image layers. Keep local writers stopped for the final snapshot.
Keep the local app stopped after cutover: two credential copies must not rotate
the same Questrade refresh token independently.

Build the app and start only the database first:

```sh
docker compose --env-file .env.aws -f compose.aws.yaml build api
docker compose --env-file .env.aws -f compose.aws.yaml up -d --wait db
```

Restore only into a fresh, empty database, with no `--clean`:

```sh
docker compose --env-file .env.aws -f compose.aws.yaml exec -T db \
  pg_restore -U aimoney -d aimoney --single-transaction --exit-on-error < data/backups/cloud-cutover.dump
```

Verify business table counts against the source. Apply the authentication migration
and manually provision the first approved email with `auth_admin.py` above.
Then start the stack:

```sh
docker compose --env-file .env.aws -f compose.aws.yaml up -d --wait
```

Verify TLS, `/signin`, unauthenticated portfolio API HTTP 401, email delivery,
invalid/expired/replayed code rejection, session cookies, sign-out, and retained
portfolio data. The minimal `/api/health` endpoint and login assets are public;
application pages, API documentation and portfolio endpoints require a session.
Start with saved captures; market refresh and paid OpenAI generation remain
explicit actions.

## Updates, rollback and backups

Back up PostgreSQL before an update. Use a reviewed commit/image and an explicit
migration before enabling authentication. Retain the previous image and proxy
configuration. During the first auth rollout keep Basic Auth in the running
proxy until the new app's session gate is verified, then reload Caddy to remove
the redundant prompt. If reverting to an app without session checks, restore
Basic Auth before admitting public traffic. The additive auth tables can remain;
never restore an old database over new portfolio writes just to roll back code.

PostgreSQL, application files and Caddy certificate volumes persist on EBS. Never
run `docker compose down -v` on the live stack. Include authentication tables in
logical database backups; preserve server secrets through a separate protected
recovery path. Scheduled S3 backup uploads and restore drills remain planned.
The pre-cutover local backup is not a substitute for recurring cloud backups.
