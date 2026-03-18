"""
Shared constants for the AICT backend.
"""

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
