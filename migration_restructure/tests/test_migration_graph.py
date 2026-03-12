"""
Test migration graph integrity.

Replaces the old test file with a cleaner version that validates:
  1. Every down_revision points to an existing revision.
  2. There is exactly one root migration (down_revision = None).
  3. The chain forms a single linear sequence (no branches/merges).
  4. Revision IDs follow the NNN_slug naming convention.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"
REVISION_PATTERN = re.compile(r"^\d{3}_[a-z][a-z0-9_]*$")


def _extract_revision_metadata(path: Path) -> tuple[str | None, str | None]:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    revision = None
    down_revision = None

    for node in module.body:
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

        if target_name == "revision" and value_node is not None:
            try:
                revision = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                pass
        elif target_name == "down_revision" and value_node is not None:
            try:
                down_revision = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                pass

    return revision, down_revision


def _all_migrations() -> list[tuple[Path, str | None, str | None]]:
    results = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        rev, down = _extract_revision_metadata(path)
        results.append((path, rev, down))
    return results


def test_down_revisions_reference_existing_migrations() -> None:
    """Every down_revision must point to a revision that exists."""
    migrations = _all_migrations()
    revisions = {rev for _, rev, _ in migrations if rev}
    missing = [
        f"{path.name}: down_revision '{down}' not found"
        for path, _, down in migrations
        if isinstance(down, str) and down not in revisions
    ]
    assert not missing, f"Broken chain:\n" + "\n".join(missing)


def test_exactly_one_root_migration() -> None:
    """There must be exactly one migration with down_revision = None."""
    migrations = _all_migrations()
    roots = [path.name for path, _, down in migrations if down is None]
    assert len(roots) == 1, (
        f"Expected exactly 1 root migration, found {len(roots)}: {roots}"
    )


def test_linear_chain() -> None:
    """Migrations form a single linear chain (no branches)."""
    migrations = _all_migrations()
    # Build a map: down_revision → list of revisions that point to it
    children: dict[str | None, list[str]] = {}
    for _, rev, down in migrations:
        children.setdefault(down, []).append(rev)

    branching = {
        parent: kids
        for parent, kids in children.items()
        if len(kids) > 1
    }
    assert not branching, (
        f"Migration chain has branches (multiple children for same parent):\n"
        + "\n".join(f"  {parent} → {kids}" for parent, kids in branching.items())
    )


def test_revision_naming_convention() -> None:
    """All revision IDs follow the NNN_slug pattern."""
    migrations = _all_migrations()
    bad = [
        f"{path.name}: revision '{rev}'"
        for path, rev, _ in migrations
        if rev and not REVISION_PATTERN.match(rev)
    ]
    assert not bad, (
        f"Revisions not matching NNN_slug pattern:\n" + "\n".join(bad)
    )
