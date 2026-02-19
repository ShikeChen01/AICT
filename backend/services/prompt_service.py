"""
Prompt service: backward-compatible façade over backend.prompts.

Orchestration lives in backend/prompts/assembly.py (PromptAssembly).
Individual block helpers live in backend/prompts/builder.py.
This module re-exports both for import compatibility.
"""

from backend.prompts.assembly import PromptAssembly  # noqa: F401
from backend.prompts.builder import (  # noqa: F401
    get_identity_block,
    get_memory_block,
    get_tool_io_block,
)
