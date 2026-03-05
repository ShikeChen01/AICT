"""Phase 21: Add pg_notify triggers for agent config changes (LISTEN/NOTIFY).

Installs PostgreSQL triggers on agents, prompt_block_configs, and tool_configs
tables.  On any UPDATE, the trigger calls pg_notify('agent_config_changed',
JSON payload) so the ConfigListener can mark the affected agent's config dirty
for a live reload without restarting the session.

Payload schema:
    {"agent_id": "<uuid>", "table": "<table_name>"}

For prompt_block_configs and tool_configs, agent_id is looked up via the FK.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "021"
down_revision = "020_sandbox_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Trigger function: fires on agents UPDATE ---
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_agent_config_changed_agents()
        RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'agent_config_changed',
                json_build_object(
                    'agent_id', NEW.id,
                    'table', 'agents'
                )::text
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_agent_config_changed_agents ON agents;
        CREATE TRIGGER trg_agent_config_changed_agents
            AFTER UPDATE ON agents
            FOR EACH ROW
            EXECUTE FUNCTION notify_agent_config_changed_agents();
    """)

    # --- Trigger function: fires on prompt_block_configs UPDATE ---
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_agent_config_changed_blocks()
        RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'agent_config_changed',
                json_build_object(
                    'agent_id', NEW.agent_id,
                    'table', 'prompt_block_configs'
                )::text
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_agent_config_changed_blocks ON prompt_block_configs;
        CREATE TRIGGER trg_agent_config_changed_blocks
            AFTER UPDATE ON prompt_block_configs
            FOR EACH ROW
            EXECUTE FUNCTION notify_agent_config_changed_blocks();
    """)

    # --- Trigger function: fires on tool_configs UPDATE ---
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_agent_config_changed_tools()
        RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'agent_config_changed',
                json_build_object(
                    'agent_id', NEW.agent_id,
                    'table', 'tool_configs'
                )::text
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_agent_config_changed_tools ON tool_configs;
        CREATE TRIGGER trg_agent_config_changed_tools
            AFTER UPDATE ON tool_configs
            FOR EACH ROW
            EXECUTE FUNCTION notify_agent_config_changed_tools();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_agent_config_changed_agents ON agents;")
    op.execute("DROP FUNCTION IF EXISTS notify_agent_config_changed_agents();")

    op.execute("DROP TRIGGER IF EXISTS trg_agent_config_changed_blocks ON prompt_block_configs;")
    op.execute("DROP FUNCTION IF EXISTS notify_agent_config_changed_blocks();")

    op.execute("DROP TRIGGER IF EXISTS trg_agent_config_changed_tools ON tool_configs;")
    op.execute("DROP FUNCTION IF EXISTS notify_agent_config_changed_tools();")
