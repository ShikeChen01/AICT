# Database Migrations

## Architecture

Migrations are managed by **Alembic** with **autogenerate** enabled. The SQLAlchemy models in `backend/db/models.py` are the single source of truth for the database schema. Migrations are derived from model diffs — never hand-written from scratch.

## Quick Reference

```bash
# Apply all pending migrations
alembic -c backend/alembic.ini upgrade head

# Create a new migration from model changes
./backend/scripts/new_migration.sh "add user avatar column"

# Roll back the last migration
alembic -c backend/alembic.ini downgrade -1

# See current revision
alembic -c backend/alembic.ini current

# See migration history
alembic -c backend/alembic.ini history --verbose

# Lint migrations (also runs in CI)
python backend/scripts/lint_migrations.py
```

## Workflow: Adding a Schema Change

1. **Edit the model** in `backend/db/models.py`.
2. **Generate the migration**: `./backend/scripts/new_migration.sh "description of change"`
3. **Review the generated file** — autogenerate is good but not perfect. Check for:
   - Correct column types (especially `JSON`, `LargeBinary`, custom types)
   - Proper `server_default` values
   - Index names matching conventions
   - Data migrations (autogenerate can't detect those)
4. **Test the round-trip**:
   ```bash
   alembic -c backend/alembic.ini upgrade head
   alembic -c backend/alembic.ini downgrade -1
   alembic -c backend/alembic.ini upgrade head
   ```
5. **Run the linter**: `python backend/scripts/lint_migrations.py`
6. **Commit** both the model change and the migration file together.

## Naming Convention

Migration files follow the pattern: `NNN_snake_case_slug.py`

- `NNN` is a zero-padded sequential number (001, 002, 003...)
- The slug is a short description in snake_case
- The revision ID inside the file matches the filename

Examples:
- `001_baseline.py`
- `002_add_user_avatar.py`
- `003_create_audit_log_table.py`

## Rules

1. **Models are truth.** Never add a column to a migration without adding it to `models.py` first.
2. **Always include downgrade().** Every migration must be reversible.
3. **One concern per migration.** Don't mix unrelated schema changes.
4. **Review autogenerate output.** It can't detect: renamed columns (sees drop+add), data migrations, custom DDL (like pgvector HNSW indexes), or `server_default` changes in some cases.
5. **No hand-written migrations** unless autogenerate literally can't express the change (e.g., raw DDL for pgvector indexes, data backfills).

## pgvector

pgvector is a hard requirement in all environments. The baseline migration creates the extension and the HNSW index. If you need to modify vector-related schema, you'll likely need raw DDL in the migration since Alembic can't render `USING hnsw (...)` natively.

## CI Checks

The following run on every PR:

- `python backend/scripts/lint_migrations.py` — validates naming, chain integrity, upgrade/downgrade presence
- `pytest backend/tests/test_migration_graph.py` — validates the revision chain is linear and unbroken

## Troubleshooting

**"Target database is not up to date"**: Run `alembic upgrade head` before generating a new migration.

**Autogenerate produces an empty migration**: Your models match the database. Either your change is already applied, or you forgot to save `models.py`.

**Merge conflicts in migrations**: If two branches both added a migration with the same NNN prefix, one branch needs to renumber. Update both the filename and the `revision` variable inside the file.
