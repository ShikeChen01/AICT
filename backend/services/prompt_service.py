"""
Prompt service: backward-compatible façade over backend.prompts.

All logic and block content live in backend/prompts/builder.py and backend/prompts/blocks/*.md.
This module is kept for import compatibility.
"""

from backend.prompts.builder import (  # noqa: F401
    build_system_prompt,
    get_identity_block,
    get_loopback_block,
    get_memory_block,
    get_summarization_block,
    get_tool_io_block,
)
