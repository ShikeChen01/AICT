#!/usr/bin/env python3
"""
Verify that Agent 1 (Data & messaging foundation) has landed.

Exit 0 if all prerequisites for Agent 2 are present; exit 1 otherwise.
Run from project root: python backend/scripts/check_agent1_landed.py
"""

import sys
from pathlib import Path

# Project root: parent of backend/
BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))


def check_file(path: Path, desc: str) -> bool:
    if path.exists():
        print(f"  OK  {desc}")
        return True
    print(f"  MISS {desc}")
    return False


def check_contains(path: Path, substring: str, desc: str) -> bool:
    if not path.exists():
        print(f"  MISS {desc} (file missing)")
        return False
    text = path.read_text(encoding="utf-8")
    if substring in text:
        print(f"  OK  {desc}")
        return True
    print(f"  MISS {desc} (expected substring not found)")
    return False


def main() -> int:
    print("Checking Agent 1 deliverables (prerequisites for Agent 2)...\n")

    ok = True

    # Core
    ok &= check_contains(
        BACKEND / "core" / "constants.py",
        "USER_AGENT_ID",
        "core/constants.py with USER_AGENT_ID",
    )

    # Message service
    ok &= check_file(
        BACKEND / "services" / "message_service.py",
        "services/message_service.py",
    )

    # Internal messaging API
    ok &= check_file(
        BACKEND / "api_internal" / "messaging.py",
        "api_internal/messaging.py",
    )

    # Public messages API
    ok &= check_file(
        BACKEND / "api" / "v1" / "messages.py",
        "api/v1/messages.py",
    )

    # Message router
    ok &= check_file(
        BACKEND / "workers" / "message_router.py",
        "workers/message_router.py",
    )

    # DB models for new tables
    models_py = BACKEND / "db" / "models.py"
    for name, desc in [
        ("channel_messages", "db/models.py: channel_messages table or ChannelMessage model"),
        ("agent_messages", "db/models.py: agent_messages table or AgentMessage model"),
        ("agent_sessions", "db/models.py: agent_sessions table or AgentSession model"),
        ("project_settings", "db/models.py: project_settings table or ProjectSettings model"),
    ]:
        ok &= check_contains(models_py, name, desc)

    # Repositories
    ok &= check_file(
        BACKEND / "db" / "repositories" / "messages.py",
        "db/repositories/messages.py",
    )
    ok &= check_file(
        BACKEND / "db" / "repositories" / "sessions.py",
        "db/repositories/sessions.py",
    )

    # Migrations: at least one migration that introduces new messaging/session tables
    migrations_dir = BACKEND / "migrations" / "versions"
    if not migrations_dir.exists():
        print("  MISS migrations/versions/")
        ok = False
    else:
        migration_files = list(migrations_dir.glob("*.py"))
        has_new_schema = False
        for m in migration_files:
            if m.name in ("env.py",):
                continue
            content = m.read_text(encoding="utf-8")
            if "channel_messages" in content or "agent_messages" in content or "project_settings" in content:
                has_new_schema = True
                break
        if has_new_schema:
            print("  OK  Migrations include channel_messages/agent_messages/project_settings")
        else:
            print("  MISS Migrations for channel_messages/agent_messages/project_settings")
            ok = False

    print()
    if ok:
        print("Agent 1 has landed. Agent 2 can proceed.")
        return 0
    print("Agent 1 deliverables are missing. Agent 2 is blocked.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
