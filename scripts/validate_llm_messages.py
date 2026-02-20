#!/usr/bin/env python3
"""
Validate that prompt orchestration output (pa.messages) is structurally valid
for every LLM provider before it reaches the API.

Catches problems like:
  - tool_use without a matching tool_result  → Anthropic 400 error
  - Consecutive same-role messages           → Anthropic 400 error
  - tool_result not in the SAME user message → Anthropic 400 error
  - Orphan tool_result blocks (silently dropped, causing confusion)
  - Missing tool call responses              → OpenAI / Gemini errors
  - Interrupted-session dangling tool_use    → most common root cause

Usage
-----
Run built-in test suite (all known failure modes):
    python scripts/validate_llm_messages.py

Validate a JSON dump of pa.messages from a live session:
    python scripts/validate_llm_messages.py --file messages.json

Show only failing test cases:
    python scripts/validate_llm_messages.py --failures-only

Disable colour output (e.g. in CI):
    python scripts/validate_llm_messages.py --no-color

Import and call from production code (pre-flight check before LLM call):
    from scripts.validate_llm_messages import validate_messages
    result = validate_messages(pa.messages)
    if not result.passed:
        for issue in result.issues:
            logger.error(issue)
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Force UTF-8 stdout on Windows (avoids cp1252 encode errors for box/arrow chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.llm.contracts import LLMMessage, LLMToolCall  # noqa: E402

# ── ANSI colours ──────────────────────────────────────────────────────────────
_USE_COLOR = True


def _color(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def red(t: str) -> str:    return _color("31", t)
def green(t: str) -> str:  return _color("32", t)
def yellow(t: str) -> str: return _color("33", t)
def cyan(t: str) -> str:   return _color("36", t)
def bold(t: str) -> str:   return _color("1",  t)


# ── Data types ────────────────────────────────────────────────────────────────
@dataclass
class Issue:
    severity: str   # "error" | "warning"
    provider: str   # "internal" | "anthropic" | "openai" | "gemini"
    index: int      # message index in the relevant format
    message: str

    def __str__(self) -> str:
        if self.severity == "error":
            icon = red("ERR ")
        else:
            icon = yellow("WARN")
        return f"  [{icon}] [{cyan(self.provider):>18}] msg[{self.index:>2}]: {self.message}"


@dataclass
class ValidationResult:
    label: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def print_result(self, show_passing: bool = True) -> None:
        status = green("PASS") if self.passed else red("FAIL")
        print(bold(f"  [{status}] {self.label}"))
        for issue in self.issues:
            print(str(issue))
        if not self.issues and show_passing:
            print(green("         No issues found."))


# ── Internal dict → LLMMessage conversion ────────────────────────────────────
def dict_to_llm_messages(raw: list[dict]) -> list[LLMMessage]:
    """Convert pa.messages (list of raw dicts) to LLMMessage objects."""
    result: list[LLMMessage] = []
    for msg in raw:
        role = msg.get("role", "")
        content = str(msg.get("content") or "")
        if role == "user":
            result.append(LLMMessage(role="user", content=content))
        elif role == "assistant":
            tcs = [
                LLMToolCall(
                    id=str(tc.get("id") or ""),
                    name=str(tc.get("name") or ""),
                    input=tc.get("input") if isinstance(tc.get("input"), dict) else {},
                )
                for tc in (msg.get("tool_calls") or [])
            ]
            result.append(LLMMessage(role="assistant", content=content, tool_calls=tcs))
        elif role == "tool":
            result.append(LLMMessage(
                role="tool",
                content=content,
                tool_use_id=str(msg.get("tool_use_id") or ""),
            ))
    return result


# ── Provider API message builders (mirror production code exactly) ────────────
def build_anthropic_messages(
    messages: list[LLMMessage],
) -> tuple[list[dict[str, Any]], set[str]]:
    """Mirror AnthropicSDKProvider._build_messages — identical logic."""
    api: list[dict[str, Any]] = []
    issued_ids: set[str] = set()

    for msg in messages:
        if msg.role == "user":
            api.append({"role": "user", "content": [{"type": "text", "text": msg.content or ""}]})

        elif msg.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if msg.content:
                blocks.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                if not tc.id or not tc.name:
                    continue
                blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input or {}})
                issued_ids.add(tc.id)
            if not blocks:
                blocks.append({"type": "text", "text": ""})
            api.append({"role": "assistant", "content": blocks})

        elif msg.role == "tool":
            tid = msg.tool_use_id or ""
            if not tid or tid not in issued_ids:
                continue  # orphan — same as production
            api.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tid, "content": str(msg.content or "")}],
            })

    return api, issued_ids


def build_openai_messages(
    system_prompt: str,
    messages: list[LLMMessage],
) -> list[dict[str, Any]]:
    """Mirror OpenAISDKProvider._build_messages — identical logic."""
    import json as _json

    api: list[dict[str, Any]] = []
    if system_prompt:
        api.append({"role": "system", "content": system_prompt})

    for msg in messages:
        if msg.role == "user":
            api.append({"role": "user", "content": msg.content or ""})
        elif msg.role == "assistant":
            entry: dict[str, Any] = {"role": "assistant"}
            if msg.content:
                entry["content"] = msg.content
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": _json.dumps(tc.input or {})},
                    }
                    for tc in msg.tool_calls
                    if tc.id and tc.name
                ]
            if "content" not in entry and "tool_calls" not in entry:
                entry["content"] = ""
            api.append(entry)
        elif msg.role == "tool":
            api.append({
                "role": "tool",
                "tool_call_id": msg.tool_use_id or "",
                "content": str(msg.content or ""),
            })

    return api


def build_gemini_contents(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Mirror GeminiProviderAdapter.complete message construction — identical logic."""
    contents: list[dict[str, Any]] = []
    issued: dict[str, str] = {}  # tool_use_id → function_name

    for msg in messages:
        if msg.role == "user":
            contents.append({"role": "user", "parts": [{"text": msg.content or ""}]})

        elif msg.role == "assistant":
            parts: list[dict[str, Any]] = []
            if msg.content:
                parts.append({"text": msg.content})
            for tc in msg.tool_calls:
                if not tc.name:
                    continue
                fc: dict[str, Any] = {"name": tc.name, "args": tc.input or {}}
                if tc.id:
                    fc["id"] = tc.id
                    issued[tc.id] = tc.name
                parts.append({"functionCall": fc})
            if parts:
                contents.append({"role": "model", "parts": parts})

        elif msg.role == "tool":
            tid = msg.tool_use_id or ""
            fn_name = issued.get(tid, "")
            if not fn_name:
                continue  # orphan — same as production
            entry: dict[str, Any] = {"id": tid} if tid else {}
            entry["name"] = fn_name
            entry["response"] = {"result": str(msg.content or "")}
            contents.append({"role": "user", "parts": [{"functionResponse": entry}]})

    return contents


# ── Validators ────────────────────────────────────────────────────────────────
def validate_internal(raw: list[dict]) -> list[Issue]:
    """
    Validate pa.messages (raw dict format) before any provider conversion.
    Catches structural problems at the source, before they propagate.
    """
    issues: list[Issue] = []
    p = "internal"

    # 1. Collect all issued tool_use IDs and the index of their assistant message
    issued: dict[str, int] = {}  # tool_use_id → msg index
    for i, msg in enumerate(raw):
        if msg.get("role") == "assistant":
            for tc in (msg.get("tool_calls") or []):
                tid = str(tc.get("id") or "")
                tname = str(tc.get("name") or "")
                if not tid:
                    issues.append(Issue("warning", p, i, f"tool_call missing 'id' (name={tname!r}) — will be skipped by providers"))
                elif not tname:
                    issues.append(Issue("warning", p, i, f"tool_call id={tid!r} missing 'name' — will be skipped by providers"))
                else:
                    issued[tid] = i

    # 2. Collect satisfied tool_use IDs
    satisfied: set[str] = set()
    for i, msg in enumerate(raw):
        if msg.get("role") == "tool":
            tid = str(msg.get("tool_use_id") or "")
            if not tid:
                issues.append(Issue("error", p, i, "tool message has no 'tool_use_id' — every tool result must reference a tool_use"))
            elif tid not in issued:
                issues.append(Issue("warning", p, i,
                    f"tool result references unknown tool_use_id={tid!r} — orphan result "
                    f"(the paired tool_use was dropped from history or never issued)"))
            else:
                satisfied.add(tid)

    # 3. Unsatisfied tool_use IDs — THIS IS THE DIRECT CAUSE OF THE 400 ERROR
    for tid, msg_idx in issued.items():
        if tid not in satisfied:
            issues.append(Issue("error", p, msg_idx,
                f"tool_use id={tid!r} has NO corresponding tool_result. "
                f"Likely cause: session was interrupted before the tool finished. "
                f"Anthropic will reject this with: 'tool_use ids were found without tool_result blocks immediately after'"))

    return issues


def validate_anthropic(api_messages: list[dict]) -> list[Issue]:
    """Validate Anthropic-formatted messages against the API's strict rules."""
    issues: list[Issue] = []
    p = "anthropic"

    if not api_messages:
        return issues

    # Rule 1: must start with 'user'
    if api_messages[0].get("role") != "user":
        issues.append(Issue("error", p, 0,
            f"First message must be role='user', got {api_messages[0].get('role')!r}"))

    # Rule 2: no consecutive same-role messages
    for i in range(1, len(api_messages)):
        prev = api_messages[i - 1].get("role")
        curr = api_messages[i].get("role")
        if prev == curr:
            issues.append(Issue("error", p, i,
                f"Consecutive '{curr}' messages — Anthropic requires strictly alternating turns. "
                f"(This often happens when an assistant calls multiple tools and each result "
                f"is sent as a separate user message instead of being merged into one.)"))

    # Rule 3: every tool_use must be immediately followed by a user message
    #          that contains matching tool_result block(s)
    issued_ids: set[str] = set()
    for i, msg in enumerate(api_messages):
        if msg.get("role") != "assistant":
            continue
        tool_use_ids = [
            b["id"]
            for b in (msg.get("content") or [])
            if b.get("type") == "tool_use" and b.get("id")
        ]
        for tid in tool_use_ids:
            issued_ids.add(tid)

        if not tool_use_ids:
            continue

        if i + 1 >= len(api_messages):
            issues.append(Issue("error", p, i,
                f"Assistant message has tool_use(s) {tool_use_ids!r} but there is no following message at all"))
            continue

        next_msg = api_messages[i + 1]
        if next_msg.get("role") != "user":
            issues.append(Issue("error", p, i + 1,
                f"Expected 'user' message with tool_result(s) after tool_use, "
                f"got role={next_msg.get('role')!r}"))
            continue

        result_ids = {
            b.get("tool_use_id")
            for b in (next_msg.get("content") or [])
            if b.get("type") == "tool_result"
        }
        for tid in tool_use_ids:
            if tid not in result_ids:
                issues.append(Issue("error", p, i,
                    f"tool_use id={tid!r} is not satisfied by the immediately following user message. "
                    f"Results found in that message: {sorted(result_ids)!r}"))

    # Rule 4: warn on orphan tool_result blocks (references unknown tool_use_id)
    for i, msg in enumerate(api_messages):
        if msg.get("role") != "user":
            continue
        for b in (msg.get("content") or []):
            if b.get("type") == "tool_result":
                tid = b.get("tool_use_id", "")
                if tid and tid not in issued_ids:
                    issues.append(Issue("warning", p, i,
                        f"tool_result references tool_use_id={tid!r} which was never issued "
                        f"(orphan — silently dropped by the production orphan filter)"))

    return issues


def validate_openai(api_messages: list[dict]) -> list[Issue]:
    """Validate OpenAI-formatted messages."""
    issues: list[Issue] = []
    p = "openai"

    # Collect issued tool_call IDs
    issued: dict[str, int] = {}
    for i, msg in enumerate(api_messages):
        if msg.get("role") == "assistant":
            for tc in (msg.get("tool_calls") or []):
                tid = tc.get("id", "")
                if tid:
                    issued[tid] = i

    # Collect satisfied IDs
    satisfied: set[str] = set()
    for i, msg in enumerate(api_messages):
        if msg.get("role") == "tool":
            tid = msg.get("tool_call_id", "")
            if tid in issued:
                satisfied.add(tid)
            elif tid:
                issues.append(Issue("warning", p, i,
                    f"tool message references unknown tool_call_id={tid!r} (orphan)"))

    for tid, msg_idx in issued.items():
        if tid not in satisfied:
            issues.append(Issue("error", p, msg_idx,
                f"tool_calls id={tid!r} has no corresponding tool message"))

    return issues


def validate_gemini(api_contents: list[dict]) -> list[Issue]:
    """Validate Gemini-formatted contents."""
    issues: list[Issue] = []
    p = "gemini"

    # Collect issued functionCall IDs
    issued: dict[str, int] = {}
    for i, content in enumerate(api_contents):
        if content.get("role") == "model":
            for part in (content.get("parts") or []):
                fc = part.get("functionCall")
                if isinstance(fc, dict):
                    fc_id = str(fc.get("id") or fc.get("name") or "")
                    if fc_id:
                        issued[fc_id] = i

    # Collect satisfied IDs
    satisfied: set[str] = set()
    for i, content in enumerate(api_contents):
        if content.get("role") == "user":
            for part in (content.get("parts") or []):
                fr = part.get("functionResponse")
                if isinstance(fr, dict):
                    fr_id = str(fr.get("id") or fr.get("name") or "")
                    if fr_id in issued:
                        satisfied.add(fr_id)
                    elif fr_id:
                        issues.append(Issue("warning", p, i,
                            f"functionResponse references unknown id={fr_id!r} (orphan)"))

    for fc_id, msg_idx in issued.items():
        if fc_id not in satisfied:
            issues.append(Issue("error", p, msg_idx,
                f"functionCall id={fc_id!r} has no corresponding functionResponse"))

    return issues


# ── Main validation entry point ───────────────────────────────────────────────
def validate_messages(
    raw_messages: list[dict],
    system_prompt: str = "",
    label: str = "messages",
) -> ValidationResult:
    """
    Validate pa.messages (internal dict format) against all providers.

    This is the primary API for both the CLI and for importing into production
    code as a pre-flight check before calling the LLM.

    Parameters
    ----------
    raw_messages:   pa.messages — list of dicts with role/content/tool_calls/tool_use_id
    system_prompt:  optional system prompt (used for OpenAI format building)
    label:          human-readable label for the ValidationResult

    Returns
    -------
    ValidationResult with all issues across internal + provider-specific checks.
    """
    result = ValidationResult(label=label)
    llm_messages = dict_to_llm_messages(raw_messages)

    # 1. Internal format checks (catches root causes early)
    result.issues.extend(validate_internal(raw_messages))

    # 2. Anthropic — build API format then validate
    anthropic_api, _ = build_anthropic_messages(llm_messages)
    result.issues.extend(validate_anthropic(anthropic_api))

    # 3. OpenAI — build API format then validate
    openai_api = build_openai_messages(system_prompt, llm_messages)
    result.issues.extend(validate_openai(openai_api))

    # 4. Gemini — build API format then validate
    gemini_api = build_gemini_contents(llm_messages)
    result.issues.extend(validate_gemini(gemini_api))

    return result


# ── Built-in test cases ───────────────────────────────────────────────────────
def _tc(tc_id: str, name: str, input_data: dict | None = None) -> dict:
    return {"id": tc_id, "name": name, "input": input_data or {"arg": "val"}}


# Each entry: (label, raw_messages, expect_pass)
TEST_CASES: list[tuple[str, list[dict], bool]] = [
    # ── VALID cases ──────────────────────────────────────────────────────────
    (
        "Valid: simple user/assistant exchange (no tools)",
        [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        True,
    ),
    (
        "Valid: single tool call with result",
        [
            {"role": "user", "content": "Read the file"},
            {"role": "assistant", "content": "", "tool_calls": [_tc("tc_1", "read_file")]},
            {"role": "tool", "content": "file contents here", "tool_use_id": "tc_1"},
            {"role": "assistant", "content": "Here is what I found."},
        ],
        True,
    ),
    (
        "Valid: multiple sequential tool calls (one per turn)",
        [
            {"role": "user", "content": "Do two things"},
            {"role": "assistant", "content": "", "tool_calls": [_tc("tc_1", "read_file")]},
            {"role": "tool", "content": "result 1", "tool_use_id": "tc_1"},
            {"role": "assistant", "content": "", "tool_calls": [_tc("tc_2", "write_file")]},
            {"role": "tool", "content": "result 2", "tool_use_id": "tc_2"},
            {"role": "assistant", "content": "All done."},
        ],
        True,
    ),
    (
        "Valid: tool call with text in assistant message",
        [
            {"role": "user", "content": "Do it"},
            {"role": "assistant", "content": "I will call the tool now.", "tool_calls": [_tc("tc_1", "read_file")]},
            {"role": "tool", "content": "file data", "tool_use_id": "tc_1"},
            {"role": "assistant", "content": "Here is what I found."},
        ],
        True,
    ),
    (
        "Valid: long tool loop (5 iterations)",
        [
            {"role": "user", "content": "Start long task"},
            *[
                msg
                for i in range(1, 6)
                for msg in [
                    {"role": "assistant", "content": "", "tool_calls": [_tc(f"tc_{i}", f"tool_{i}")]},
                    {"role": "tool", "content": f"result {i}", "tool_use_id": f"tc_{i}"},
                ]
            ],
            {"role": "assistant", "content": "All done."},
        ],
        True,
    ),
    (
        "Valid: multi-turn conversation with interspersed tool calls",
        [
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Thinking...", "tool_calls": [_tc("tc_1", "search")]},
            {"role": "tool", "content": "search result", "tool_use_id": "tc_1"},
            {"role": "assistant", "content": "Based on that..."},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Let me check.", "tool_calls": [_tc("tc_2", "read_file")]},
            {"role": "tool", "content": "file data", "tool_use_id": "tc_2"},
            {"role": "assistant", "content": "Done."},
        ],
        True,
    ),

    # ── FAILING cases — root cause: interrupted session ───────────────────────
    (
        "FAIL: tool_use with NO result — session interrupted before tool completed",
        [
            {"role": "user", "content": "Do something"},
            # Session crashed / was restarted after this assistant message was saved to DB
            {"role": "assistant", "content": "", "tool_calls": [_tc("tc_dangling", "read_file")]},
            # ← tool_result for tc_dangling was NEVER saved to DB
            {"role": "user", "content": "New message in next session"},
            {"role": "assistant", "content": "Ok."},
        ],
        False,
    ),
    (
        "FAIL: multiple tool_uses, only first result saved (partial interruption)",
        [
            {"role": "user", "content": "Do two things"},
            {"role": "assistant", "content": "", "tool_calls": [
                _tc("tc_1", "read_file"),
                _tc("tc_2", "write_file"),
            ]},
            # tc_1 completed and was saved; process died before tc_2 result was saved
            {"role": "tool", "content": "result 1", "tool_use_id": "tc_1"},
            {"role": "assistant", "content": "Done."},
        ],
        False,
    ),
    (
        "FAIL: all tool_uses from interrupted session, completely missing results",
        [
            {"role": "user", "content": "Earlier message"},
            {"role": "assistant", "content": "Previous good response."},
            {"role": "user", "content": "Next message"},
            {"role": "assistant", "content": "", "tool_calls": [
                _tc("tc_x", "tool_a"),
                _tc("tc_y", "tool_b"),
            ]},
            # Both results missing — session killed after LLM responded but before any tool ran
        ],
        False,
    ),

    # ── FAILING cases — root cause: history truncation / orphan results ────────
    (
        "WARN (not error): orphan tool_result — provider silently drops it, conversation continues",
        [
            {"role": "user", "content": "Continuing conversation"},
            # Orphan result — its paired assistant tool_use was in an older session
            # that got truncated out of the history window.
            # The production orphan filter silently drops this, so the API call succeeds,
            # but it is flagged here as a WARNING so you know data was silently lost.
            {"role": "tool", "content": "stale result", "tool_use_id": "tc_stale"},
            {"role": "assistant", "content": "Answer."},
        ],
        True,  # passes (only warnings, not errors) — provider drops the orphan cleanly
    ),

    # ── FAILING cases — structural / role ordering ────────────────────────────
    (
        "FAIL: consecutive user messages",
        [
            {"role": "user", "content": "Message 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response"},
        ],
        False,
    ),
    (
        "FAIL: conversation starts with assistant (no leading user message)",
        [
            {"role": "assistant", "content": "Starting without user prompt"},
            {"role": "user", "content": "User follows"},
        ],
        False,
    ),
    (
        "FAIL: tool_use with result BUT followed immediately by another tool_use (no user gap)",
        [
            {"role": "user", "content": "Start"},
            {"role": "assistant", "content": "", "tool_calls": [_tc("tc_1", "read_file")]},
            {"role": "tool", "content": "result", "tool_use_id": "tc_1"},
            # Missing: the assistant's NEXT message should be here, not another tool turn
            # but the real issue below is tc_3 has no result
            {"role": "assistant", "content": "", "tool_calls": [_tc("tc_3", "write_file")]},
            # tc_3 result missing
            {"role": "assistant", "content": "Done."},  # ← consecutive assistant messages
        ],
        False,
    ),
]


# ── CLI ───────────────────────────────────────────────────────────────────────
def main() -> None:
    global _USE_COLOR  # noqa: PLW0603

    parser = argparse.ArgumentParser(
        description="Validate LLM message lists for all providers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--file", "-f",
        metavar="PATH",
        help="JSON file containing a list of message dicts (pa.messages format)",
    )
    parser.add_argument(
        "--failures-only",
        action="store_true",
        help="Only print failing test cases",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colour output",
    )
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        _USE_COLOR = False

    # ── File mode ────────────────────────────────────────────────────────────
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(red(f"File not found: {path}"), file=sys.stderr)
            sys.exit(1)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(red(f"Invalid JSON: {exc}"), file=sys.stderr)
            sys.exit(1)
        if not isinstance(raw, list):
            print(red("JSON file must contain a list of message dicts"), file=sys.stderr)
            sys.exit(1)

        result = validate_messages(raw, label=str(path))
        result.print_result(show_passing=True)
        print()
        sys.exit(0 if result.passed else 1)

    # ── Test suite mode ───────────────────────────────────────────────────────
    show_passing = not args.failures_only

    print(bold(f"\n{'-' * 68}"))
    print(bold("  LLM Message Orchestration Validator -- Built-in Test Suite"))
    print(bold(f"{'-' * 68}\n"))

    unexpected_count = 0

    for label, messages, expect_pass in TEST_CASES:
        result = validate_messages(messages, label=label)
        actual_pass = result.passed
        is_expected = actual_pass == expect_pass

        if not is_expected:
            unexpected_count += 1
            result.label = (
                f"{label}  "
                + red(f"<-- UNEXPECTED ({'PASS' if actual_pass else 'FAIL'})")
            )

        if not show_passing and actual_pass and expect_pass:
            continue

        result.print_result(show_passing=show_passing)
        print()

    # Summary
    total = len(TEST_CASES)
    passed_count = sum(
        1 for _, m, e in TEST_CASES
        if validate_messages(m).passed == e
    )

    print(bold(f"{'-' * 68}"))
    print(
        bold("Results: ")
        + green(f"{passed_count}/{total} match expected")
        + (red(f"  |  {unexpected_count} unexpected") if unexpected_count else "")
    )
    print()

    sys.exit(0 if unexpected_count == 0 else 1)


if __name__ == "__main__":
    main()
