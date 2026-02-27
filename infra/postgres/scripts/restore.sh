#!/usr/bin/env bash
# restore.sh — Restore an AICT Postgres database from a pg_dump backup.
#
# Usage:
#   sudo ./restore.sh /opt/postgres/backups/aict_20260226_030000.sql.gz
#
# WARNING: This drops and recreates the database. All current data will be lost.

set -euo pipefail

COMPOSE_DIR="/opt/postgres/compose"
DUMP_FILE="${1:?Usage: restore.sh <dump-file>}"

if [ ! -f "${DUMP_FILE}" ]; then
    echo "ERROR: File not found: ${DUMP_FILE}"
    exit 1
fi

source "${COMPOSE_DIR}/.env"

echo "[restore] Restoring from: ${DUMP_FILE}"
echo "[restore] WARNING: This will DROP and recreate database '${POSTGRES_DB}'."
read -p "[restore] Continue? (y/N) " -r
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "[restore] Aborted."
    exit 0
fi

echo "[restore] Dropping and recreating database..."
docker exec aict-postgres psql -U "${POSTGRES_USER}" -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};" \
    -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

echo "[restore] Running pg_restore..."
docker exec -i aict-postgres pg_restore \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" \
    --no-owner \
    --role="${POSTGRES_USER}" \
    < "${DUMP_FILE}"

echo "[restore] Done. Database '${POSTGRES_DB}' restored from ${DUMP_FILE}."
