#!/usr/bin/env bash
set -euo pipefail
umask 077
mkdir -p /backups
while true; do
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  temp="/backups/rocky-${stamp}.dump.partial"
  if pg_dump -Fc --file="$temp" && pg_restore --list "$temp" >/dev/null; then
    mv "$temp" "/backups/rocky-${stamp}.dump"
    printf 'Database backup verified: %s\n' "$stamp"
  else
    printf 'Database backup FAILED: %s\n' "$stamp" >&2
    exit 1
  fi
  sleep "${BACKUP_INTERVAL_SECONDS:-86400}"
done
