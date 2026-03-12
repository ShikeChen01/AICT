#!/usr/bin/env python3
"""
Migration linter — run in CI to catch common mistakes.

Checks:
  1. Every migration file has both upgrade() and downgrade() functions.
  2. Revision IDs follow the NNN_slug pattern (e.g. "001_baseline").
  3. The down_revision chain is unbroken (no dangling references).
  4. No duplicate revision IDs.
  5. No use of op.execute() with unparameterized raw SQL (warning only).

Usage:
  python -m backend.scripts.lint_migrations
  # or in CI:
  python backend/scripts/lint_migrations.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"
REVISION_PATTERN = re.compile(r"^\d{3}_[a-z][a-z0-9_]*$")

_errors: list[str] = []
_warnings: list[str] = []


def _err(path: Path, msg: str) -> None:
    _errors.append(f"  ERROR  {path.name}: {msg}")


def _warn(path: Path, msg: str) -> None:
    _warnings.append(f"  WARN   {path.name}: {msg}")


def _extract_metadata(path: Path) -> dict:
    """Parse a migration file and extract revision, down_revision, and function names."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    result: dict = {"revision": None, "down_revision": None, "functions": set()}

    for node in tree.body:
        # Extract top-level assignments
        target_name = None
        value_node = None

        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                target_name = target.id
                value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value

        if target_name in ("revision", "down_revision") and value_node is not None:
            try:
                result[target_name] = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                pass

        # Extract function definitions
        if isinstance(node, ast.FunctionDef):
            result["functions"].add(node.name)

    return result


def lint() -> int:
    migration_files = sorted(VERSIONS_DIR.glob("*.py"))

    if not migration_files:
        print("No migration files found. Nothing to lint.")
        return 0

    all_revisions: dict[str, Path] = {}
    all_down_refs: list[tuple[Path, str]] = []

    for path in migration_files:
        if path.name == "__init__.py":
            continue

        meta = _extract_metadata(path)

        # ── Check 1: upgrade() and downgrade() present ───────────
        if "upgrade" not in meta["functions"]:
            _err(path, "missing upgrade() function")
        if "downgrade" not in meta["functions"]:
            _err(path, "missing downgrade() function")

        # ── Check 2: revision ID format ──────────────────────────
        rev = meta["revision"]
        if rev is None:
            _err(path, "no `revision` variable found")
            continue

        if not REVISION_PATTERN.match(rev):
            _err(path, f"revision '{rev}' doesn't match NNN_slug pattern (e.g. '002_add_users')")

        # ── Check 3: collect for chain validation ────────────────
        if rev in all_revisions:
            _err(path, f"duplicate revision ID '{rev}' (also in {all_revisions[rev].name})")
        all_revisions[rev] = path

        down = meta["down_revision"]
        if isinstance(down, str):
            all_down_refs.append((path, down))
        elif isinstance(down, tuple):
            for d in down:
                if d:
                    all_down_refs.append((path, d))

        # ── Check 5: raw SQL warning ────────────────────────────
        source = path.read_text(encoding="utf-8")
        # Only warn about op.execute with string literals (not text())
        raw_sql_hits = re.findall(r'op\.execute\(\s*["\']', source)
        if raw_sql_hits:
            _warn(path, f"found {len(raw_sql_hits)} raw SQL op.execute() call(s) — "
                        "consider using sa.text() for parameterization")

    # ── Check 4: unbroken chain ──────────────────────────────────
    for path, down_rev in all_down_refs:
        if down_rev not in all_revisions:
            _err(path, f"down_revision '{down_rev}' not found in any migration file")

    # ── Report ───────────────────────────────────────────────────
    if _warnings:
        print("Warnings:")
        for w in _warnings:
            print(w)
        print()

    if _errors:
        print("Errors:")
        for e in _errors:
            print(e)
        print(f"\n{len(_errors)} error(s) found.")
        return 1

    print(f"All {len(all_revisions)} migration(s) passed lint checks.")
    return 0


if __name__ == "__main__":
    sys.exit(lint())
