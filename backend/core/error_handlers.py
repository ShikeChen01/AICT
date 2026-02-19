"""
FastAPI exception handlers.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from backend.core.exceptions import (
    AICTException,
    AgentNotFoundError,
    GitOperationBlocked,
    GitOperationFailed,
    InvalidAgentRole,
    InvalidTaskStatus,
    MaxEngineersReached,
    ProjectNotFoundError,
    SandboxNotFoundError,
    ScopeViolationError,
    TaskNotFoundError,
)

_NOT_FOUND = (TaskNotFoundError, AgentNotFoundError, ProjectNotFoundError, SandboxNotFoundError)
_FORBIDDEN = (GitOperationBlocked, ScopeViolationError)
_BAD_REQUEST = (InvalidAgentRole, InvalidTaskStatus, MaxEngineersReached)


async def aict_exception_handler(request: Request, exc: AICTException) -> JSONResponse:
    error_type = type(exc).__name__

    if isinstance(exc, _NOT_FOUND):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, _FORBIDDEN):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, _BAD_REQUEST):
        code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, GitOperationFailed):
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        code = status.HTTP_400_BAD_REQUEST

    return JSONResponse(
        status_code=code,
        content={
            "detail": str(exc),
            "type": error_type,
            "error_type": error_type,
            "message": str(exc),
            "path": request.url.path,
        },
    )
