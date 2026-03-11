"""027: Add composite indexes on Agent and Task hot query paths.

Missing indexes identified during code review:
  - Agent(project_id, status): used by list_agents, worker checks, agent spawning
  - Agent(project_id, role): used by spawn_engineer role filtering
  - Task(project_id, status): used by kanban queries, task board, assignment logic

Revision ID: 027
Revises: 026
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic
revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_agents_project_status", "agents", ["project_id", "status"])
    op.create_index("ix_agents_project_role", "agents", ["project_id", "role"])
    op.create_index("ix_tasks_project_status", "tasks", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_tasks_project_status", table_name="tasks")
    op.drop_index("ix_agents_project_role", table_name="agents")
    op.drop_index("ix_agents_project_status", table_name="agents")
