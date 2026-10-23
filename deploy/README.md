# Manual AWS deployment — us-west-2

Target: one EC2 instance, Elastic IP, existing Route 53 hosted zone, Caddy HTTPS,
`aimoney` application image and PostgreSQL. The selected subdomain is `aimoney`;
the full domain is still needed. No AWS resources have been created by these files.

## 1. Create EC2 manually

In the EC2 console select **US West (Oregon), us-west-2** and launch:

| Setting | Value |
| --- | --- |
| Name | aimoney |
| AMI | Official Ubuntu Server 24.04 LTS, 64-bit x86 |
| Instance type | t3.medium (2 vCPU, 4 GiB) |
| Key pair | Create/select your SSH key; keep the private key locally |
| Network | Public subnet with an internet-gateway route |
| Auto-assign public IP | Enabled initially; associate Elastic IP afterward |
| Storage | 30 GiB gp3, encrypted; retain data volume/root disk on termination if desired |
| Metadata | Require IMDSv2 |
| Security group | TCP 22 from your IP only; TCP 80 and 443 from the internet |

Do not open 8765 or 5432. Allocate and associate an Elastic IP. In your existing
Route 53 public hosted zone create an **A record**, name `aimoney`, value the Elastic
IP, alias off, TTL 300. Preserve other domain records. Do not run the cloud stack
on the developer machine; it uses ports 80/443 and your real hostname.

## 2. Prepare the instance

Install Docker Engine and the Compose plugin using the official Ubuntu instructions:
https://docs.docker.com/engine/install/ubuntu/ . Enable Docker at boot. The SSH user
needs access to Docker; log out and back in after changing group membership.

Clone the repository on EC2 (use an SSH agent or authorized Git access, never put
a Git token in a command URL). Use the current committed revision. Work from the
repository root. Prepare persistent paths before starting containers:

```sh
mkdir -p data reports .secrets models/financials/cibc_fx/artifacts
chmod 700 .secrets
cp deploy/aws.env.example .env.aws
chmod 600 .env.aws
```

Edit `.env.aws` locally on EC2. Set the full hostname and a fresh PostgreSQL password;
set UID/GID to the SSH user's `id -u` / `id -g`. Generate a web-login hash interactively:

```sh
docker run --rm -it caddy:2 caddy hash-password
```

Save the hash as a single-quoted `AUTH_HASH` in `.env.aws`. The cleartext login
password is not stored in the repository. All application routes, records and API
documentation are behind Caddy's HTTPS Basic Authentication. This is a single-user
deployment, not multi-user account isolation. Do not log `.env.aws` or render the
resolved Compose environment into terminal/chat output.

## 3. Transfer the current data, then restore

Take a fresh `pg_dump -Fc` from the local PostgreSQL container. Transfer that dump,
`data/` holdings JSON, `reports/` saved captures, required `.secrets/` configuration
and optional FX model artifacts over SSH to the matching EC2 directories. These
are private runtime files excluded from Git. A Git clone alone is insufficient.

Keep all local portfolio writers stopped during the final snapshot and transfer.
Keep the local application stopped after cloud cutover: Questrade rotates its
refresh token, so two independent credential copies must not refresh concurrently.
Do not copy Docker's database volume files while PostgreSQL is running.

On EC2, build and start only the database first:

```sh
docker compose --env-file .env.aws -f compose.aws.yaml build api
docker compose --env-file .env.aws -f compose.aws.yaml up -d --wait db
```

Restore into the **fresh, empty** cloud database (no `--clean`):

```sh
docker compose --env-file .env.aws -f compose.aws.yaml exec -T db \
  pg_restore -U aimoney -d aimoney --single-transaction --exit-on-error < data/backups/cloud-cutover.dump
```

If restore fails, leave the API stopped and resolve the cause. Verify table counts
against the source before enabling the web application. Existing cloud records
must be reviewed before attempting another restore.

## 4. Start and verify

After DNS points to the Elastic IP:

```sh
docker compose --env-file .env.aws -f compose.aws.yaml up -d --wait
```

Visit `https://aimoney.YOUR_DOMAIN` and log in. Caddy obtains and renews certificates;
ports 80/443 must reach this instance. Verify unauthorized HTTPS requests get 401,
authenticated `/api/health` responds 200, saved holdings and analyses load, scenario
controls work, and a reviewed settings edit persists. Start with saved captures;
quote refresh and OpenAI assessments are explicit actions.

Only Caddy publishes ports. The application keeps one Uvicorn worker, uses the
explicit HTTPS origin and ignores untrusted forwarded headers. Database and
certificate volumes persist on the instance's EBS disk. Stop EC2 between sessions;
never use `docker compose down -v` on the live stack.

Take logical PostgreSQL backups and copy them off the instance (planned S3 bucket).
Validate restoration to a separate database. Removing EC2 storage or Docker volumes
can remove the only copy if off-instance backups have not been configured.

## Updating the app

Back up PostgreSQL first, update to a reviewed Git commit, then build and replace
only the application container with the same `.env.aws` and volume configuration.
Future schema changes need explicit migrations; a new image alone is not a schema
migration. Retain a previous image tag for rollback. PostgreSQL and Caddy data must
not be recreated during an application update.
