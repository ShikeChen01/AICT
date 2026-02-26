"""Unit tests for prompt assembly (blocks + PromptAssembly)."""

from pathlib import Path

import pytest

from backend.services.prompt_service import (
    PromptAssembly,
    get_identity_block,
    get_memory_block,
)


def test_get_identity_block_manager(sample_manager, sample_project) -> None:
    block = get_identity_block(sample_manager, sample_project.name)
    assert "General Manager" in block or "GM" in block
    assert sample_project.name in block


def test_get_identity_block_cto(sample_cto, sample_project) -> None:
    block = get_identity_block(sample_cto, sample_project.name)
    assert "CTO" in block or "Chief Technology" in block
    assert sample_project.name in block


def test_get_identity_block_engineer(sample_engineer, sample_project) -> None:
    block = get_identity_block(sample_engineer, sample_project.name)
    assert "Engineer" in block
    assert sample_engineer.display_name in block
    assert sample_project.name in block


def test_get_memory_block_empty() -> None:
    block = get_memory_block(None)
    assert "No memory recorded yet" in block


def test_get_memory_block_content() -> None:
    block = get_memory_block("Key decisions: use REST API.")
    assert "Key decisions" in block


def test_loopback_block() -> None:
    pa = PromptAssembly.__new__(PromptAssembly)
    pa.messages = []
    pa.append_loopback()
    assert len(pa.messages) == 1
    msg = pa.messages[0]
    assert msg["role"] == "user"
    assert "END" in msg["content"]
    assert "without calling any tools" in msg["content"]


def test_summarization_block() -> None:
    block = PromptAssembly.get_summarization_block()
    assert "update_memory" in block
    assert "read_history" in block


def test_system_prompt_manager(sample_manager, sample_project) -> None:
    pa = PromptAssembly(sample_manager, sample_project, None)
    assert sample_project.name in pa.system_prompt
    assert "END" in pa.system_prompt
    assert "update_memory" in pa.system_prompt
    assert "No memory recorded yet" in pa.system_prompt


def test_system_prompt_cto(sample_cto, sample_project) -> None:
    pa = PromptAssembly(sample_cto, sample_project, None)
    assert sample_project.name in pa.system_prompt
    assert "CTO" in pa.system_prompt or "Chief Technology" in pa.system_prompt
    assert "END" in pa.system_prompt
    assert "No memory recorded yet" in pa.system_prompt


def test_system_prompt_engineer(sample_engineer, sample_project) -> None:
    pa = PromptAssembly(sample_engineer, sample_project, "active task: fix tests")
    assert sample_project.name in pa.system_prompt
    assert "Engineer" in pa.system_prompt
    assert sample_engineer.display_name in pa.system_prompt
    assert "active task: fix tests" in pa.system_prompt


def test_system_prompt_block_order(sample_manager, sample_project) -> None:
    """Identity and Tool IO should appear after Memory, Rules, Thinking."""
    pa = PromptAssembly(sample_manager, sample_project, None)
    prompt = pa.system_prompt
    memory_pos = prompt.find("No memory recorded yet")
    identity_pos = prompt.find("General Manager")
    if identity_pos == -1:
        identity_pos = prompt.find("GM")
    assert memory_pos < identity_pos, "Memory should come before Identity"


def test_append_tool_result() -> None:
    pa = PromptAssembly.__new__(PromptAssembly)
    pa.messages = []
    pa._current_iteration_tool_result_chars = 0
    pa.append_tool_result("test_tool", "success output", "tid-1")
    assert len(pa.messages) == 1
    msg = pa.messages[0]
    assert msg["role"] == "tool"
    assert msg["content"] == "success output"
    assert msg["tool_use_id"] == "tid-1"


def test_append_tool_error() -> None:
    pa = PromptAssembly.__new__(PromptAssembly)
    pa.messages = []
    pa._current_iteration_tool_result_chars = 0
    pa.append_tool_error("bad_tool", RuntimeError("boom"), "tid-2")
    assert len(pa.messages) == 1
    msg = pa.messages[0]
    assert msg["role"] == "tool"
    assert "bad_tool" in msg["content"]
    assert "boom" in msg["content"]
    assert "next_action" in msg["content"]


def test_append_end_solo_warning() -> None:
    pa = PromptAssembly.__new__(PromptAssembly)
    pa.messages = []
    pa.append_end_solo_warning()
    assert len(pa.messages) == 1
    msg = pa.messages[0]
    assert msg["role"] == "tool"
    assert "END was called alongside other tools" in msg["content"]
    assert msg["tool_use_id"] == "end-solo-rule"


def test_append_assistant() -> None:
    pa = PromptAssembly.__new__(PromptAssembly)
    pa.messages = []
    pa.append_assistant("hello", [{"id": "tc1", "name": "end", "input": {}}])
    assert len(pa.messages) == 1
    msg = pa.messages[0]
    assert msg["role"] == "assistant"
    assert msg["content"] == "hello"
    assert msg["tool_calls"] == [{"id": "tc1", "name": "end", "input": {}}]


def test_all_block_files_loadable_and_non_empty() -> None:
    """Regression: all .md block files must exist and have content."""
    blocks_dir = Path(__file__).parent.parent / "prompts" / "blocks"
    expected_files = [
        "rules.md",
        "history_rules.md",
        "incoming_message_rules.md",
        "tool_result_rules.md",
        "thinking.md",
        "tool_io_base.md",
        "tool_io_manager.md",
        "tool_io_cto.md",
        "tool_io_engineer.md",
        "loopback.md",
        "end_solo_warning.md",
        "summarization.md",
        "memory_template.md",
        "identity_manager.md",
        "identity_cto.md",
        "identity_engineer.md",
    ]
    for filename in expected_files:
        path = blocks_dir / filename
        assert path.exists(), f"Block file missing: {filename}"
        content = path.read_text(encoding="utf-8")
        assert content.strip(), f"Block file is empty: {filename}"
