"""Merge pgvector and mainline migration branches.

Revision ID: 029_merge_pgvector_and_mainline
Revises: 025_enable_pgvector_column, 028_sandbox_table
Create Date: 2026-03-12
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "029_merge_pgvector_and_mainline"
down_revision: tuple[str, str] = ("025_enable_pgvector_column", "028_sandbox_table")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge branches; no schema changes."""


def downgrade() -> None:
    """Split branches; no schema changes."""
