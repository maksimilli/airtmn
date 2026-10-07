#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backup_dir="$(pwd)/backups"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
archive="catalog-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
# Stop writes so the SQLite snapshot and all referenced PDFs belong to the same state.
was_running=$(docker compose ps --status running --services app)
restart_app() { if [[ "$was_running" == app ]]; then docker compose start app; fi; }
trap restart_app EXIT
docker compose stop app
docker compose run --rm --no-deps --user 0 -v "$backup_dir:/backups" \
  -e BACKUP_UID="$(id -u)" -e BACKUP_GID="$(id -g)" -e BACKUP_FILE="$archive" app \
  sh -c 'python deploy/backup.py create --archive "/backups/$BACKUP_FILE" && chmod 600 "/backups/$BACKUP_FILE" && chown "$BACKUP_UID:$BACKUP_GID" "/backups/$BACKUP_FILE"'
printf 'Backup saved: %s\n' "$backup_dir/$archive"
