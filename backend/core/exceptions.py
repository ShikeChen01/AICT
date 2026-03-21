"""
Custom exceptions for AICT.
"""


class AICTException(Exception):
    """Base exception for AICT."""

    pass


class TaskNotFoundError(AICTException):
    def __init__(self, task_id):
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")


class AgentNotFoundError(AICTException):
    def __init__(self, agent_id):
        self.agent_id = agent_id
        super().__init__(f"Agent {agent_id} not found")


class ProjectNotFoundError(AICTException):
    def __init__(self, project_id):
        self.project_id = project_id
        super().__init__(f"Project {project_id} not found")


class GitOperationBlocked(AICTException):
    """Raised when a blocked git operation is attempted."""

    pass


class GitOperationFailed(AICTException):
    """Raised when a git operation fails."""

    pass


class SandboxNotFoundError(AICTException):
    def __init__(self, agent_id):
        self.agent_id = agent_id
        super().__init__(f"Sandbox for agent {agent_id} not found")


class ScopeViolationError(AICTException):
    """Raised when an agent tries to access outside their scope."""

    pass


class MaxEngineersReached(AICTException):
    """Raised when trying to spawn an engineer beyond the limit."""

    def __init__(self, limit: int = 5):
        self.limit = limit
        super().__init__(f"Maximum number of engineers ({limit}) reached")


class InvalidAgentRole(AICTException):
    def __init__(self, role: str):
        self.role = role
        super().__init__(f"Invalid agent role: {role}")


class InvalidTaskStatus(AICTException):
    def __init__(self, status: str):
        self.status = status
        super().__init__(f"Invalid task status: {status}")


class TierLimitError(AICTException):
    """Raised when a user exceeds their subscription tier limits."""

    def __init__(self, message: str, current_tier: str = "free", upgrade_url: str = "/settings/billing"):
        self.current_tier = current_tier
        self.upgrade_url = upgrade_url
        super().__init__(message)
