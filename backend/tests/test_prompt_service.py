"""Unit tests for PromptService (block assembly)."""

from pathlib import Path

import pytest

from backend.services.prompt_service import (
    build_system_prompt,
    get_identity_block,
    get_memory_block,
    get_loopback_block,
    get_summarization_block,
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


def test_get_loopback_block() -> None:
    block = get_loopback_block()
    assert "END" in block
    assert "without calling any tools" in block


def test_get_summarization_block() -> None:
    block = get_summarization_block()
    assert "update_memory" in block
    assert "read_history" in block


def test_build_system_prompt(sample_manager, sample_project) -> None:
    prompt = build_system_prompt(sample_manager, sample_project, None)
    assert sample_project.name in prompt
    assert "END" in prompt
    assert "update_memory" in prompt
    assert "No memory recorded yet" in prompt


def test_build_system_prompt_cto(sample_cto, sample_project) -> None:
    prompt = build_system_prompt(sample_cto, sample_project, None)
    assert sample_project.name in prompt
    assert "CTO" in prompt or "Chief Technology" in prompt
    assert "END" in prompt
    assert "No memory recorded yet" in prompt


def test_build_system_prompt_engineer(sample_engineer, sample_project) -> None:
    prompt = build_system_prompt(sample_engineer, sample_project, "active task: fix tests")
    assert sample_project.name in prompt
    assert "Engineer" in prompt
    assert sample_engineer.display_name in prompt
    assert "active task: fix tests" in prompt


def test_all_block_files_loadable_and_non_empty() -> None:
    """Regression: all .md block files must exist and have content."""
    blocks_dir = Path(__file__).parent.parent / "prompts" / "blocks"
    expected_files = [
        "rules.md",
        "thinking.md",
        "tool_io_base.md",
        "tool_io_manager.md",
        "tool_io_cto.md",
        "tool_io_engineer.md",
        "loopback.md",
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
