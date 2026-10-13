# Deploy Rocky’s with Vercel, PostgreSQL and Resend

The app has a native Django Vercel configuration and a Resend HTTPS mail backend. These are prepared locally, not deployed or connected to a live mail service. Vercel does not run the supplied Docker Compose database/backup containers or retain `.local` data. Do not use the local database URL for Vercel.

1. **Vercel → Add New → Project:** import `Temtech/Rocky` from GitHub. Select Django and set the root to the directory containing `manage.py` and `vercel.json`. The application source is included in this repository; private cloud database files and credentials are excluded. Use Production and a separate Preview environment.
2. **Vercel Marketplace → PostgreSQL:** provision a hosted PostgreSQL database (Neon is one option), connect it to the project and obtain its connection URL. Set `DATABASE_URL` explicitly to the provider’s URL. Use the provider-supported pooled connection URL for runtime/serverless traffic and a direct connection for migrations/restoration. Do not silently substitute the local PostgreSQL address. Set `DB_SSLMODE=verify-full` with the provider's supported trust configuration. Serverless connections use `CONN_MAX_AGE=0`.
3. **Resend → Domains:** add your sending domain and publish the exact DNS records shown by Resend in your DNS provider. Wait for Resend verification. Choose a real address under that verified domain as `DEFAULT_FROM_EMAIL`; this is not necessarily a mailbox account. Do not assume a suggested address is verified.
4. **Resend → API Keys:** create a sending-only key scoped to the verified domain where available. Enter it securely in Vercel → Project → Settings → Environment Variables as `RESEND_API_KEY`. Never put it in GitHub, source files or chat.
5. Set the following Vercel **Production** variables before building. Use a separate database/key/host for Preview; do not connect untrusted previews to production employee data.

| Variable | Value |
|---|---|
| `DEBUG` | `0` |
| `DJANGO_SECRET_KEY` | Strong generated secret; keep stable across redeployments |
| `DATABASE_URL` | Hosted PostgreSQL URL, including credentials, entered securely |
| `DB_SSLMODE` | `verify-full` with the database provider’s trust configuration |
| `ALLOWED_HOSTS` | `rockyworldwide.vercel.app` |
| `CSRF_TRUSTED_ORIGINS` | `https://rockyworldwide.vercel.app` |
| `EMAIL_PROVIDER` | `resend` |
| `RESEND_API_KEY` | Resend sending key, entered securely |
| `DEFAULT_FROM_EMAIL` | Approved sender under a Resend-verified domain |

Vercel’s platform-assigned `VERCEL_URL` is additionally allowed for that specific deployment. No wildcard trust of other tenants' vercel.app hosts is used. SMTP settings are unnecessary when `EMAIL_PROVIDER=resend`.

6. **Migrations and existing accounts:** from a trusted local/CI administration environment, inject the production key and a direct database URL securely, then run `python manage.py migrate --noinput`. Alternatively, restore a private backup into a **new empty database first**, validate it, then apply migrations. The current five accounts exist only in this cloud workspace’s database; Vercel does not automatically copy them. Do not expose an HTTP migration/restore endpoint or run migrations on every serverless invocation. After migration, bootstrap an authorized manager with the interactive `bootstrap_accounts` command if using a fresh database; invite the others through management. To retain the configured initial accounts and history, transfer the private backup through a trusted provider-supported restoration procedure.
7. Deploy. Native Vercel Django detection reads `manage.py`/the WSGI settings and collects static assets. It does not run `scripts/dev.sh`. Use the project’s `rockyworldwide.vercel.app` production alias. This Vercel-owned address does not require rockylimos.com DNS changes. Ensure this hostname is assigned to the intended Vercel project under its domain settings. Then update exact host/origin variables and redeploy if necessary.
8. Verify login, first-password change, dispatcher/management access, shift actions, database persistence after redeployment, and Resend invitation/reset acceptance and **actual recipient mailbox delivery**. Resend API acceptance alone does not establish inbox delivery; inspect delivery/bounce events. The app returns neutral forgot-password responses and preserves failure notices for administration.
9. Enable hosted database backups, retention and recovery drills with the database provider. The cloud machine’s daily backup container does not run on Vercel. Arrange an independent scheduled backup job/provider service and encrypted off-host storage as required.

## Current limits

The chosen app hostname is `rockyworldwide.vercel.app`. The hosted PostgreSQL connection and Resend key/verified sender have not been supplied. No Vercel deployment, production migration, real email send or recipient delivery has been verified. The D01–D60 workbook and exact original logo asset remain separate pending inputs.

## Implementation evidence

Vercel native Django framework support was checked against the official `vercel/vercel` source (`packages/frameworks/src/frameworks.ts` and `packages/python/src/index.ts`). Direct documentation access was blocked by this cloud network, so live platform setup must still be checked in your Vercel project. Resend mail uses its HTTPS `POST https://api.resend.com/emails` endpoint with bearer authentication, a verified sender, and acceptance-ID validation; failures do not log message bodies, reset tokens or API keys.

The application explicitly trusts `rockyworldwide.vercel.app` and its HTTPS origin, even if older host environment values are still present. Other configured hosts are preserved; unrelated Vercel tenant hostnames are not trusted.
