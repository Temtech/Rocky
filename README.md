# Rocky’s Operations Workspace

This project is maintained on [`main`](https://github.com/Temtech/Rocky/tree/main) in `Temtech/Rocky`. Make project changes and deployments from `main`. The `dispatch-tracker` branch is intentionally empty. Configure the Vercel project’s Production Branch / Branch Tracking as `main`; changing a Git branch alone does not change Vercel settings. The application address is `rockyworldwide.vercel.app`.

A runnable Django 5.2 / PostgreSQL 16 application for Rocky’s Worldwide Chauffeured Transportation. Ground Alliance remains the system for reservations, chauffeurs, trips and flights. This application records attendance, operational exceptions, downtime research/outreach, summaries and handoffs.

## Run locally

Requirements: Python 3.12+, Docker, and a free local port 5432. All commands run from the checkout root.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
./scripts/dev.sh
```

The local launcher starts a daily verified-backup container as well as the database and application. The local database binds only to loopback. Its data lives in `.local/pgdata`; it uses trust authentication **only for isolated local development**. `DEBUG=1` generates a local, ignored secret key with restrictive permissions. Use authenticated PostgreSQL and HTTPS in production.

In the current cloud machine, the Python environment is `/workspace/rocky-venv`. Run `ROCKY_PYTHON=/workspace/rocky-venv/bin/python ./scripts/dev.sh`. No seed passwords, real email addresses or credential values are committed to the source. The five requested accounts have been provisioned in the current database; all require a first-login password change. Snapshots/backups of that database contain sensitive employee/account data and must stay private.

No public registration exists. A new deployment starts with no accounts unless the existing database is restored. Bootstrap an authorized manager interactively:

```bash
DEBUG=1 .venv/bin/python manage.py bootstrap_accounts --name 'Your manager' --email 'actual-address@your-domain' --role management
```

The command prompts for a hidden, validated password. Create additional employees through Management → Employees → Invite employee once SMTP is connected. The same command can provision the requested Noah/Umer dispatcher and Ezekiel/Teddy/Betty management roles without a default password.

## Dispatcher instructions

1. Sign in using your employee email. Change an initial password when prompted.
2. Read your assigned schedule, operating guidance and management instructions.
3. Start Shift / Working. Use Start Break and End Break / Return to Work for each actual break. Close an open break before End Shift.
4. Record only operational exceptions, with an owner, next action and deadline. Existing unresolved issues carry forward under the same ID.
5. In downtime, research affiliates/drivers using approved criteria; research does not constitute approval. Research marketing prospects using approved targeting/template. Confirm an actual email send separately, after sending in the approved mailbox. This app does **not** send marketing mail.
6. End Shift when work actually ends. Submit a daily summary and handoff separately; delayed closeout does not change attendance. Reports populate from existing source records. Copy the email-ready report into your approved channel.
7. Review incoming handoffs and acknowledge those addressed to you. Only the current recipient may acknowledge.
8. Account & Security supports password changes and revoking other sessions.

Active Dispatch → Exceptions and Follow-Ups → Affiliate/Driver Verification → Cold Email Marketing. Stop downtime work immediately for operational responsibilities.

## Management instructions

- Overview separates filtered shift-period activity from unresolved backlog. Filters cover employee, dates, attendance, management review and duty state. Coverage polls the backend every 15 seconds. The last successful synchronization and connection failures remain visible.
- Employees: create/invite, change roles, revoke sessions, deactivate or reactivate. Deactivation retains history, reassigns pending incoming handoffs and unresolved owned issues, and requires an explicit decision to close an active shift using server time.
- Schedules & Leave: enter complete Denver dates/times, including the next date for overnight end times. An ambiguous/nonexistent daylight-saving local time requires an explicit offset. Schedules already attached to attendance cannot be edited. Future schedules and approved leave are excluded from missed-shift warnings.
- Operating Policies: configure grace, permitted break and approaching-deadline warning minutes; approved verification criteria; marketing targeting/template; management instructions; optional payroll-policy description. No targets or composite performance scores are invented. Net hours are not labeled paid hours.
- Duties: import source workbook, set the operational section, evidence mapping and guidance-only behavior, activate/deactivate, and assign to individuals, named dispatcher groups or all dispatchers with explicit effective dates, cadence, weekdays, deadline and optional recorded condition. Changes affect subsequent shift starts and retain historical duty versions/assignments. Routine Ground Alliance guidance does not create a daily 60-item checklist.
- Verification approvals, duty evidence review, attendance review and timestamp corrections require management permission. Correction reasons are mandatory and original timestamps/events remain intact. Existing submitted reports stay as snapshots; revised reports are separate revisions.
- Audit History shows meaningful business changes and actors without passwords, reset tokens or SMTP secrets. Database triggers prohibit edits/deletions of audit records, shift events, duty versions, summary revisions, corrections and confirmed sends.

## D01–D60 import

**The actual source workbook was not attached. No production D01–D60 descriptions have been fabricated.**

Upload CSV/XLSX in Management → Duties → Import source workbook, or:

```bash
DEBUG=1 .venv/bin/python manage.py import_duties /secure/path/source.xlsx --manager-email actual-manager@example.com
```

The importer requires one sheet with these headers (case-insensitive): `code`, `description`, `instructions`, `frequency`; optional `section`. It preserves the full cell text and original frequency. If the actual workbook uses different headers/layout, a layout adapter must be added after inspecting that file; no arbitrary extraction is attempted. It must contain D01–D60 exactly once, with no missing/duplicate/additional duty IDs. Validation happens before an atomic import. Reimporting identical source text is a no-op; conflicting source duties cannot be overwritten. The register shows reconciliation and unmapped evidence warnings. Imported duties are initially **unassigned**; management must set reliable applicability/cadence and evidence mappings rather than guessing from free-text frequency.

## Email and account recovery

Set these server-side environment variables: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` (normally 1), `EMAIL_USE_SSL` (normally 0), `DEFAULT_FROM_EMAIL`. SMTP port 465 requires SSL=1/TLS=0. Use an approved authenticated SMTP service, a verified sending domain/address, and its required network destination. No real SMTP credentials were provided, so no invitations or reset emails have been delivered from this cloud instance.

Forgot Password returns a neutral response. Links are secure, single-use and expire in one hour. Resetting revokes previous sessions. Invited accounts have unusable passwords until setup. Management can initiate a reset but cannot retrieve a password. Login/reset attempts are database-rate-limited. Argon2 salted password hashes are used. First-login passwords must be changed. Keep SMTP credentials in deployment secrets; never commit `.env`.

Test delivery is verified through Django's in-memory email backend, **not a real external mailbox**. Validate actual delivery and spam filtering after connecting SMTP.

## Deployment

`Dockerfile`, `compose.yaml` and `Caddyfile` provide an HTTPS deployment path, with persistent PostgreSQL and Caddy volumes. No public deployment connection/domain was supplied, so a live public URL has not been created.

1. Copy `.env.example` to `.env` and fill a strong `DJANGO_SECRET_KEY`, unique `POSTGRES_PASSWORD`, PostgreSQL `DATABASE_URL` (Compose database hostname `db`), real `APP_DOMAIN`/`ALLOWED_HOSTS`, and SMTP settings securely. Percent-encode credentials in the database URL. For managed databases, use their TLS CA configuration and `DB_SSLMODE=verify-full`.
2. Point the real domain to your host and open ports 80/443. Start the database and build the app: `docker compose up -d db` and `docker compose build app`.
3. Apply schema and static assets before starting public traffic: `docker compose run --rm app python manage.py migrate --noinput` then `docker compose run --rm app python manage.py collectstatic --noinput`. To retain generated static files in the running image, the Compose app startup command performs collection as well.
4. Restore your private database backup or bootstrap a manager using `docker compose run --rm app python manage.py bootstrap_accounts ...`.
5. `docker compose up -d`. Validate HTTPS, role redirects, SMTP delivery, and the intended workflow using a restricted test account. Complete `manage.py check --deploy` with the production settings.
6. The included `backups` service generates a verified PostgreSQL archive at startup and every 24 hours. Copy encrypted backups to durable off-host storage, configure retention/monitoring and perform recovery drills. A volume alone is not a backup.

Production secrets stay on the server. Caddy terminates TLS; Django requires secure cookies and HTTPS outside DEBUG. Application access logging is disabled to avoid logging reset-link secrets; application diagnostic logging redacts reset paths. Keep any upstream proxy access logs from recording token-bearing URLs.

## Database and recovery

Migrations are in `operations/migrations`. UUIDs are stable. Foreign keys use history-preserving protection. Partial unique constraints enforce one active shift per employee and one open break per shift. PostgreSQL triggers enforce matching employees and shift/break boundaries, block Do Not Contact sends, and keep original timestamps/historical records immutable. All business writes use transactions, server time, role/record-scoped querysets, CSRF protection, and audited changes. Attendance and business-form requests have persisted idempotency keys; the same submission replays its committed result and conflicting reuse is rejected.

UTC timestamps are authoritative. Denver dates/offsets use the IANA `America/Denver` zone. Final elapsed/net hours remain incomplete until shift end. Completed break totals and live estimates are labeled separately. Summary snapshots are immutable while current source calculations reflect approved attendance corrections.

Local backup:

```bash
./scripts/backup.sh
# Restore to a NEW database first, never overwrite the live database blindly:
docker exec rocky-postgres createdb -U rocky rocky_recovery
# Substitute the intended private archive path:
docker exec -i rocky-postgres pg_restore --exit-on-error --no-owner -U rocky -d rocky_recovery < .local/backups/your-archive.dump
```

Verify employee, shift, break, summary, handoff and audit counts, then run representative functional checks against the restored database. Only after verification and stopping writes should an authorized operator switch the application database connection. The included local archive is private, ignored by Git, and contains the initial employee accounts.

For Compose production: `docker compose exec -T db pg_dump -U rocky -d rocky -Fc > private-backup.dump`; protect the archive with restrictive filesystem permissions and encryption. Use provider-managed encrypted backups where available. Restore with `pg_restore --exit-on-error --no-owner` into a separate database and verify the same records. The Compose `backups` service and local launcher schedule verified archives every 24 hours. They retain all completed archives; monitor disk usage. Define retention, encryption, off-host replication and recovery objectives with the deployment owner; off-host storage is not configured automatically.

## Testing

```bash
DEBUG=1 .venv/bin/python manage.py test operations --noinput
```

These integration tests use a disposable PostgreSQL test database. See `TEST_REPORT.md`. Chromium end-to-end tests are in `scripts/browser_test.py`; they explicitly refuse to operate unless `DATABASE_URL` points to `rocky_e2e`. They require Playwright and a local Chromium executable; start a separate test server on port 8001 against that database, then run the script. Test fixtures never modify the real employees or operational database.

## Branding

Navy `#1b3b64`, off-white and dark backgrounds follow the supplied brand image. `static/logo.svg` is a proportion-preserving vector reconstruction from the inline reference, **not the original logo asset**. Replace it with the original SVG/PNG when supplied for exact lettering/mark fidelity. Responsive desktop/mobile screenshots are in the ignored `test-results` directory after browser tests.

## Remaining external inputs

- Actual D01–D60 source workbook, followed by reconciliation and management applicability configuration.
- Original downloadable logo asset for exact fidelity.
- Approved SMTP service credentials/network access and verified sender, followed by real delivery tests.
- Production hosting/domain/database connection and encrypted off-host backup storage, followed by deployment and recovery validation.

The local app is runnable; the above external steps have not been claimed as completed or production-verified.

## Building inside this cloud proxy

The cloud build was verified with an optional BuildKit CA secret taken from the platform-installed trust store. Certificate verification remains enabled; the private build trust mount is not retained in the application image. Ordinary networks can use `docker build .` without this optional mount. In this cloud network:

```bash
ROCKY_PROXY_IP=$(python -c 'import socket; print(socket.gethostbyname("proxy"))')
DOCKER_CONFIG=/tmp/rocky-docker docker build --network host --add-host "proxy:$ROCKY_PROXY_IP" --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY --secret id=build_ca,src=/etc/ssl/certs/ca-certificates.crt -t rocky-operations:local .
```

Never replace a certificate verification failure with an insecure download flag.

## Vercel and Resend

For the selected hosting/email providers, follow [VERCEL_RESEND_SETUP.md](VERCEL_RESEND_SETUP.md). Native Django configuration is in `vercel.json`; the Resend API backend is selected with `EMAIL_PROVIDER=resend`. This path uses external hosted PostgreSQL and provider backups, rather than the local Docker services. Live credentials, domain configuration, account transfer and actual delivery/deployment validation are still required.
