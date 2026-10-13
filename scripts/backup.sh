#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Local Docker database. Production: use pg_dump with securely injected PG* variables.
mkdir -p .local/backups
umask 077
file=".local/backups/rocky-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker exec rocky-postgres pg_dump -U rocky -d rocky -Fc > "$file"
docker exec -i rocky-postgres pg_restore --list < "$file" >/dev/null
printf 'Verified backup archive: %s\n' "$file"
