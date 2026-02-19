"""
Shared constants for the AICT backend.

Reserved UUID for the user in channel_messages (from_agent_id / target_agent_id).
This UUID never exists in the agents table.
"""

from uuid import UUID

# Reserved UUID representing the user in channel_messages.
# Used when from_agent_id or target_agent_id refers to the human user.
USER_AGENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000000")

# Valid agent roles
AGENT_ROLES = ("manager", "cto", "engineer")

# Valid agent statuses
AGENT_STATUSES = ("sleeping", "active", "busy")

# Valid channel message types
CHANNEL_MESSAGE_TYPES = ("normal", "system")

# Valid channel message statuses
CHANNEL_MESSAGE_STATUSES = ("sent", "received")

# Valid agent session statuses
AGENT_SESSION_STATUSES = ("running", "completed", "force_ended", "error")

# Valid agent session end reasons
AGENT_SESSION_END_REASONS = (
    "normal_end",
    "max_iterations",
    "max_loopbacks",
    "interrupted",
    "aborted",
    "error",
)
