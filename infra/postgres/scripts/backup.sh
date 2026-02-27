#!/usr/bin/env bash
# backup.sh — Dump the AICT Postgres database to a timestamped file.
# Run manually or via cron. Example crontab entry (daily at 3 AM UTC):
#   0 3 * * * /opt/postgres/compose/scripts/backup.sh >> /var/log/pg-backup.log 2>&1

set -euo pipefail

COMPOSE_DIR="/opt/postgres/compose"
BACKUP_DIR="${1:-/opt/postgres/backups}"
RETENTION_DAYS="${2:-7}"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
DUMP_FILE="${BACKUP_DIR}/aict_${TIMESTAMP}.sql.gz"

# Load credentials
source "${COMPOSE_DIR}/.env"

mkdir -p "${BACKUP_DIR}"

echo "[backup] Starting pg_dump at $(date -u +%Y-%m-%dT%H:%M:%SZ)..."

docker exec aict-postgres pg_dump \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" \
    --format=custom \
    --compress=6 \
    > "${DUMP_FILE}"

SIZE=$(du -h "${DUMP_FILE}" | cut -f1)
echo "[backup] Dump written: ${DUMP_FILE} (${SIZE})"

# Prune old backups
DELETED=$(find "${BACKUP_DIR}" -name "aict_*.sql.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    echo "[backup] Pruned ${DELETED} backup(s) older than ${RETENTION_DAYS} days."
fi

echo "[backup] Done."
