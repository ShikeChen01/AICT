from __future__ import annotations

import ast
from pathlib import Path


def _migration_versions_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _extract_revision_metadata(path: Path) -> tuple[str | None, str | tuple[str, ...] | None]:
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
            revision = ast.literal_eval(value_node)
        elif target_name == "down_revision" and value_node is not None:
            down_revision = ast.literal_eval(value_node)

    return revision, down_revision


def test_alembic_down_revisions_reference_existing_migrations() -> None:
    revisions: set[str] = set()
    down_revisions: list[tuple[Path, str]] = []

    for path in _migration_versions_dir().glob("*.py"):
        revision, down_revision = _extract_revision_metadata(path)
        if revision:
            revisions.add(revision)
        if isinstance(down_revision, str):
            down_revisions.append((path, down_revision))
        elif isinstance(down_revision, tuple):
            down_revisions.extend((path, item) for item in down_revision if item)

    missing = [
        f"{path.name}: {down_revision}"
        for path, down_revision in down_revisions
        if down_revision not in revisions
    ]

    assert not missing, f"Missing Alembic down_revision targets: {missing}"
