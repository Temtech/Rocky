# Dispatcher tracker repository instructions

This project uses the `main` branch in `Temtech/Rocky`.

- Work, commit and push on `main`. The user has returned this project to `main` and requested that `dispatch-tracker` remain empty unless they explicitly change this instruction.
- Verify the working branch and preserve existing changes before making edits. Use the existing checkout; cloud tasks are already isolated. Do not create a worktree unless requested.
- Production app hostname: `rockyworldwide.vercel.app`. Vercel must track `main` for this project; never assume a Git branch switch changes Vercel project settings.
- Keep credentials, `.env`, `.local`, database data and private backups out of commits. Templates containing variable names and blank values are permitted.
- Preserve historical attendance, duties, summary revisions and audit records. Keep role and record authorization enforced in the backend.
- See README.md and VERCEL_RESEND_SETUP.md for startup and deployment. Production requires hosted PostgreSQL, migrations, transferred/bootstrap accounts and a verified Resend sender/key.
