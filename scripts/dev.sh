#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export DEBUG=1
export DATABASE_URL="${DATABASE_URL:-postgresql://rocky@127.0.0.1:5432/rocky}"
mkdir -p .local
if ! docker container inspect rocky-postgres >/dev/null 2>&1; then
  docker run -d --name rocky-postgres -e POSTGRES_DB=rocky -e POSTGRES_USER=rocky -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:5432:5432 -v "$(pwd)/.local/pgdata:/var/lib/postgresql/data" postgres:16 >/dev/null
else
  docker start rocky-postgres >/dev/null
fi
for ((attempt=0; attempt<30; attempt++)); do
  if docker exec rocky-postgres pg_isready -U rocky -d rocky >/dev/null; then break; fi
  sleep 1
done
PYTHON="${ROCKY_PYTHON:-.venv/bin/python}"
# If process/container metadata was not restored, recover the private archive only
# into a database with no application schema. Never overwrite existing records.
ROCKY_SCHEMA=$(docker exec rocky-postgres psql -U rocky -d rocky -tAc "SELECT to_regclass('public.operations_user')")
if [[ -z "$ROCKY_SCHEMA" && -d .local/backups ]]; then
  ROCKY_ARCHIVE=$(find .local/backups -maxdepth 1 -name '*.dump' -type f -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)
  if [[ -n "$ROCKY_ARCHIVE" ]]; then
    docker exec -i rocky-postgres pg_restore --exit-on-error --no-owner -U rocky -d rocky < "$ROCKY_ARCHIVE"
  fi
fi
"$PYTHON" manage.py migrate --noinput
mkdir -p .local/backups
if ! docker container inspect rocky-backups >/dev/null 2>&1; then
  docker run -d --name rocky-backups --network host --user "$(id -u):$(id -g)" -e PGHOST=127.0.0.1 -e PGDATABASE=rocky -e PGUSER=rocky -v "$(pwd)/.local/backups:/backups" -v "$(pwd)/scripts/production_backup.sh:/usr/local/bin/rocky-backup:ro" --entrypoint bash postgres:16 /usr/local/bin/rocky-backup >/dev/null
else
  docker start rocky-backups >/dev/null
fi
"$PYTHON" manage.py collectstatic --noinput
exec "${PYTHON%/python}/gunicorn" rocky.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 30 --access-logfile /dev/null --pid .local/app.pid
