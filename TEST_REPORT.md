# Rocky’s application validation

Date: 2026-10-13. Executed in the cloud machine with Python 3.12, Django 5.2.18, PostgreSQL 16 and Chromium. Tests use isolated databases; the requested employee accounts and operational database were not used as fixtures.

## Results

| Check | Result | Evidence and limits |
|---|---|---|
| Django/PostgreSQL integration suite | **43 passed**, 0 failed, 0 skipped | `DEBUG=1 /workspace/rocky-venv/bin/python manage.py test operations --noinput`; current run executed all tests, returned exit 0 and destroyed its temporary database. |
| Dispatcher/management login and permissions | Passed | Role redirects; private attendance API and productivity scoping; management-only approvals/settings; CSRF enforcement; mandatory first-password change. Case-insensitive email login and database email uniqueness tested. |
| Attendance and breaks | Passed | All actions, two breaks, invalid transitions, immutable originals, incomplete final values, server-time authority, foreign-employee break rejection, duplicate-active-shift constraints. |
| Concurrent/idempotent writes | Passed | Three simultaneous start requests created one shift/event; same-key replay; conflicting reuse rejected; duplicate business forms, outreach sends and summary submissions saved once. Threaded test connections are explicitly closed, including teardown. |
| Denver time | Passed | UTC durations and Denver offsets across spring-forward, fall-back and an overnight shift. Ambiguous/nonexistent local schedule inputs require an explicit offset. |
| Duties and history | Passed | Automatic assignment, conditional applicability, named groups/inactive groups, future assignments excluded, historical duty versions and assignment revisions retained, source-evidence invalidation on research changes. |
| D01–D60 import engine | Passed **with a generated test workbook** | Exactly 60 IDs, complete text/frequency preservation, identical reimport no-op, malformed import rejected atomically. **The real source workbook is absent and has NOT been reconciled/imported.** |
| Exceptions | Passed | Required next action, text booking leading zeros, resolution timestamp, reopening, owner changes and audited history. Older unresolved backlog remains visible outside selected date filters. |
| Verification/outreach | Passed | Management approval authorization; research separate from approval; stable reviews; prospect entry does not count as sent; explicit employee-confirmed send events; distinct-contact totals; Do Not Contact blocked in application and database. |
| Summaries/handoffs/corrections | Passed | Summary snapshots/revisions, actual end unchanged by delayed closeout, authorized recipient acknowledgment, original/previous/effective timestamp retention, recalculation and append-only history. |
| Employee administration | Passed | New invitation/account setup; session revocation; deactivation/active shift closure; history retained; pending handoff and issue reassignment. |
| Password/reset behavior | Passed using test email transport | Invitation/reset mail captured in Django's in-memory backend, new password setup, single-use and expired links, neutral unknown-email response, password change, session revocation and rate limits. **No real SMTP service or recipient mailbox delivery was verified.** |
| Full browser workflow | Passed | Chromium → real HTTP server → Django → PostgreSQL: both dashboards, two breaks, exception, verification, prospect, confirmed send, shift end, summary, handoff, acknowledgment and management approval. Browser JavaScript errors checked. |
| Browser security/failure behavior | Passed | Initial-password API lockout; password change; blocked form POST preserves entered description/next action and re-enables submission; mobile sign-out accessible. Polling failures show a stale/failed connection state rather than a healthy zero. |
| Responsive layout | Passed | Desktop 1440px and mobile 390px screenshots; mobile document has no horizontal overflow. Scrollable tables/navigation retained. |
| Application/database restart persistence | Passed | Database container replaced from a cleanly stopped copy in retained `.local/pgdata`; application workers restarted; browser confirmed ended attendance, summary revision and acknowledgment remained. Current five account roles/activation/change-password flags verified after restart. |
| Backup/recovery | Passed locally | Private PostgreSQL custom archive generated and checked; restored into a separate recovery database; initial five employee and five audit records verified. A daily backup container is running and emitted a verified completion. **Encrypted off-host replication and disaster recovery on a production host remain unconfigured.** |
| Docker image | Passed | Built with pinned direct requirements. Cloud proxy required its trusted CA bundle via an optional ephemeral BuildKit mount; TLS verification stayed enabled. Production-mode container served the login form/static CSS with HTTPS/security headers. |
| Production configuration checks | Passed with one optional warning | `manage.py check --deploy` reports only `security.W021` (HSTS preload registration is not enabled). Real domain/hosting/SMTP and complete production deployment remain unverified. |
| Migrations/static/startup | Passed | Schema applied to real and test databases, no missing model migrations, static assets collected, saved launcher exercised and restarted successfully. Compose structure and shell/JavaScript syntax validated. |

## Findings resolved during implementation

- Corrected a PostgreSQL trigger that referenced a field absent from verification/prospect records.
- Adjusted the referrer policy after actual Chromium form submissions exposed an Origin/CSRF mismatch.
- Fixed author CSS overriding HTML hidden action buttons; valid shift controls now reflect server state.
- Added explicit closure of threaded test connections so test-database teardown completes cleanly.
- Preserved server-rendered success/error notices when progressive form submissions redirect, and kept inputs on connection failure.
- Supplied the platform trust store to proxied Docker builds instead of bypassing certificate verification.

## External acceptance work still required

1. Supply the actual duty workbook. Reconcile D01–D60 against the source and configure frequencies/applicability/evidence mappings. The test workbook never populates production duties.
2. Replace the SVG reconstruction with the original downloadable logo for exact brand fidelity.
3. Configure authenticated SMTP and a verified sender. Verify real invitation/reset delivery to approved recipients and mailbox/spam behavior. No real reset messages have been sent.
4. Configure production domain/host and database credentials, publish/deploy, verify HTTPS and role workflows in that deployment, and set encrypted off-host backup storage/retention/monitoring. No public application URL or production-readiness claim is made.
5. Review/save the cloud environment configuration draft, then publish the environment to retain this prepared snapshot. Environment publication is separate from public application deployment; restoration in a new task has not been independently tested.

## Vercel / Resend preparation follow-up

The selected production hostname is `dispatch.rockylimos.com`. Native `vercel.json` configuration and a Resend HTTPS mail backend have been added. The full integration suite now passes **43 tests**, including four mail-backend tests for request construction/acceptance IDs, missing keys, unconfirmed responses and sanitized provider errors. Those mail tests use a mocked HTTP transport; they do not establish real Resend acceptance or mailbox delivery. Vercel framework detection was checked in its official source repository, but no live Vercel build or deployment has been executed. A hosted PostgreSQL connection, production project access, DNS configuration, Resend key and verified sender are still required. Setup instructions and a non-secret Vercel variable template are included.
