# Desktop Tools — Design Spec

## Problem

Sandbox and desktop are two fundamentally different things:

| | Sandbox (headless) | Desktop (VM) |
|---|---|---|
| **Owner** | Agent-owned | User-owned |
| **Lifecycle** | Ephemeral, auto-provisioned via `sandbox_start_session` | Persistent, created/assigned via UI |
| **Purpose** | Code execution, shell commands | GUI automation, browser interaction |
| **Display** | Xvfb 1024x768 (no real GUI) | Full Ubuntu desktop 1920x1080 + Chrome + VNC |
| **Boot** | ~2-3s Docker container | ~180s QEMU/KVM sub-VM |
| **Agent access** | Always available, agent provisions on demand | Only when user assigns one via UI |

Today they're coupled: `Agent.sandbox` is a single `uselist=False` relationship to a `Sandbox` row. An agent cannot simultaneously have a headless sandbox AND a desktop. The existing `sandbox_*` GUI tools technically work on desktops due to `_resolve_host_port` routing, but the model prevents an agent from using both at once.

An agent should be able to:
1. Provision and use a headless sandbox for code execution (existing behavior)
2. Simultaneously use a desktop VM assigned to it for GUI automation
3. Decide independently when to use each

Desktop tools must be a completely separate tool set with their own access path to the agent's desktop.

## Design

### DB model: Two filtered relationships on Agent

Currently:
```python
class Agent(Base):
    sandbox = relationship("Sandbox", back_populates="agent", uselist=False)
```

Change to:
```python
class Agent(Base):
    sandbox = relationship(
        "Sandbox",
        primaryjoin=lambda: and_(Agent.id == Sandbox.agent_id, Sandbox.unit_type == "headless"),
        foreign_keys=lambda: [Sandbox.agent_id],
        uselist=False,
        viewonly=True,
        overlaps="desktop",
    )
    desktop = relationship(
        "Sandbox",
        primaryjoin=lambda: and_(Agent.id == Sandbox.agent_id, Sandbox.unit_type == "desktop"),
        foreign_keys=lambda: [Sandbox.agent_id],
        uselist=False,
        viewonly=True,
        overlaps="sandbox",
    )
```

Both point to the same `Sandbox` table, filtered by `unit_type`. An agent can have one of each simultaneously.

`viewonly=True` because two relationships write to the same FK column (`Sandbox.agent_id`). All mutations go through `SandboxService` which sets `agent_id` directly on the `Sandbox` row. The existing `set_committed_value(agent, "sandbox", ...)` calls in `sandbox_service.py` continue to work — `set_committed_value` operates on instance state regardless of `viewonly`.

### Migration: Partial unique index

A migration IS required. Add a partial unique index to enforce at most one sandbox per `(agent_id, unit_type)`:

```sql
CREATE UNIQUE INDEX uq_sandbox_agent_unit_type
  ON sandboxes (agent_id, unit_type)
  WHERE agent_id IS NOT NULL;
```

Without this, `uselist=False` would silently pick an arbitrary row if duplicates exist. The index makes the invariant explicit at the DB level.

### Service layer changes

`SandboxService` Path 2 methods (`execute_command`, `take_screenshot`, `mouse_move`, etc.) already accept a `Sandbox` object and route correctly via `_resolve_host_port`. No new service methods needed.

Changes needed in existing service code:

1. **`acquire_sandbox_for_agent`** — Add `Sandbox.unit_type == "headless"` filter to the existing query. Currently queries all sandboxes for the agent.

2. **`set_committed_value` calls** — Three places in `sandbox_service.py` do `set_committed_value(agent, "sandbox", ...)`. These continue to work correctly because `acquire_sandbox_for_agent` only provisions headless sandboxes, and `set_committed_value` operates on instance state directly.

3. **`release_agent_sandbox`** — Already operates on the sandbox passed to it. No change needed.

### API serialization impact

`agents.py` reads `agent.sandbox` in 5 places to serialize `sandbox_id` in API responses. After the split, this only returns the headless sandbox. Need to also expose the desktop:

```python
# Before
sandbox_id=str(agent.sandbox.id) if agent.sandbox else None,

# After
sandbox_id=str(agent.sandbox.id) if agent.sandbox else None,
desktop_id=str(agent.desktop.id) if agent.desktop else None,
```

The `AgentResponse` Pydantic model needs a new `desktop_id: str | None` field.

`task_service.py` compares `agent.sandbox` before/after for WS broadcast — should also track `agent.desktop` changes.

### Tools: Separate `desktop_*` tool set

10 new tools. 5 mirror the existing `sandbox_*` GUI tools, 5 are desktop-specific convenience tools.

**GUI tools** (mirror `sandbox_*`, operate on `ctx.agent.desktop`):

| Tool | Description | Delegates to |
|---|---|---|
| `desktop_screenshot` | Capture desktop display | `SandboxService.take_screenshot(desktop)` |
| `desktop_mouse_move` | Move cursor | `SandboxService.mouse_move(desktop, x, y)` |
| `desktop_mouse_click` | Click at position | `SandboxService.mouse_click(desktop, ...)` |
| `desktop_mouse_scroll` | Scroll at position | `SandboxService.mouse_scroll(desktop, ...)` |
| `desktop_keyboard_press` | Key press or type text | `SandboxService.keyboard_press(desktop, ...)` |

**Convenience tools** (desktop-only operations):

| Tool | Description | Implementation |
|---|---|---|
| `desktop_open_url` | Open URL in Chrome | `SandboxService.execute_command(desktop, "google-chrome ...")` |
| `desktop_list_windows` | List open windows | `SandboxService.execute_command(desktop, "wmctrl -l -p")` |
| `desktop_focus_window` | Focus window by title or ID | `SandboxService.execute_command(desktop, "wmctrl -a ...")` |
| `desktop_get_clipboard` | Read clipboard text | `SandboxService.execute_command(desktop, "xclip ...")` |
| `desktop_set_clipboard` | Write text to clipboard | `SandboxService.execute_command(desktop, "... | xclip")` |

All 10 tools share a `_require_desktop(ctx)` guard:
```python
def _require_desktop(ctx: RunContext) -> Sandbox:
    desktop = ctx.agent.desktop
    if not desktop:
        raise ToolExecutionError(
            "No desktop assigned — ask the user to assign a desktop to this agent.",
            error_code=ToolExecutionError.SANDBOX_UNAVAILABLE,
        )
    return desktop
```

### Registry

New `_DESKTOP_TOOL_NAMES` frozenset, separate from `_SANDBOX_TOOL_NAMES`. Both gated on `_sandbox_available()` (checks if VM backend is configured — both tool sets need the VM host).

```python
_DESKTOP_TOOL_NAMES = frozenset({
    "desktop_screenshot",
    "desktop_mouse_move",
    "desktop_mouse_click",
    "desktop_mouse_scroll",
    "desktop_keyboard_press",
    "desktop_open_url",
    "desktop_list_windows",
    "desktop_focus_window",
    "desktop_get_clipboard",
    "desktop_set_clipboard",
})
```

Desktop tools appear in the agent's tool list even when no desktop is assigned. The agent discovers them, and `_require_desktop` returns a clear error if called without one.

### Desktop VM image dependencies

The convenience tools require these packages in the desktop VM image:
- `wmctrl` — window listing/focus
- `xclip` — clipboard read/write
- `google-chrome` — already present

Add `wmctrl` and `xclip` to `sandbox/scripts/build_desktop_image.sh`.

## File changes

| File | Change |
|---|---|
| `backend/db/models.py` | Split `Agent.sandbox` into `sandbox` (headless) + `desktop` (desktop) filtered relationships with `overlaps` |
| `backend/migrations/versions/0XX_desktop_unique_idx.py` | Add partial unique index on `(agent_id, unit_type) WHERE agent_id IS NOT NULL` |
| `backend/tools/executors/desktop.py` | New file — 10 executor functions + `_require_desktop` guard |
| `backend/tools/tool_descriptions.json` | Add 10 `desktop_*` tool definitions |
| `backend/tools/loop_registry.py` | Import desktop executors, add `_DESKTOP_TOOL_NAMES`, register in `_TOOL_EXECUTORS` |
| `backend/services/sandbox_service.py` | Add `unit_type='headless'` filter in `acquire_sandbox_for_agent` |
| `backend/api/v1/agents.py` | Add `desktop_id` to `AgentResponse` and all 5 serialization sites |
| `backend/services/task_service.py` | Track `agent.desktop` changes for WS broadcast |
| `sandbox/scripts/build_desktop_image.sh` | Add `wmctrl`, `xclip` packages |
| `backend/tests/test_desktop_tools.py` | New file — desktop tool tests |
| `backend/tests/test_sandbox_service.py` | Update for relationship split |
| `backend/tests/test_sandbox_tools.py` | Verify sandbox tools only see headless |

## What stays the same

- `sandbox_start_session` provisions headless only (no change)
- `sandbox_*` tools continue using `ctx.agent.sandbox` (headless only)
- `SandboxService` Path 2 methods accept any `Sandbox` object (no change)
- `_resolve_host_port` routes desktop calls through pool manager proxy (no change)
- Desktop creation and assignment via REST API / UI (no change)
- Desktop assignment invariants: one agent per desktop, enforced by existing `assign_to_agent` check

## Tests

### Model / ORM
- Agent with only headless → `agent.sandbox` works, `agent.desktop` is `None`
- Agent with only desktop → `agent.desktop` works, `agent.sandbox` is `None`
- Agent with both → both relationships resolve to correct objects
- Partial unique index rejects duplicate `(agent_id, unit_type)` rows

### Desktop tool executors
- `_require_desktop` returns desktop object when assigned
- `_require_desktop` raises `ToolExecutionError` when no desktop assigned
- Each of the 10 `desktop_*` tools delegates to correct `SandboxService` method with the desktop object
- `desktop_screenshot` returns `ScreenshotResult` (same as `sandbox_screenshot`)

### Sandbox tool isolation
- Agent with desktop-only: `sandbox_*` tools error with "no active sandbox"
- Agent with headless-only: `desktop_*` tools error with "no desktop assigned"
- Agent with both: each tool set operates on its own resource independently

## GPT review points explicitly rejected

- **Command injection in shell-based tools**: The agent already has `execute_command` with unrestricted root shell access. There is no trust boundary between the agent and the sandbox. Basic quoting for correctness (avoiding accidental breakage from special characters), not security.
- **Rename `_sandbox_available()`**: Bikeshedding. It means "VM backend is configured." Both sandbox and desktop tools need the VM. The name is clear in the only context it's used.
- **Desktop assignment invariants / concurrency**: `assign_to_agent` already enforces one-agent-per-desktop via `if sandbox.agent_id is not None: raise SandboxAlreadyAssigned`. If user unassigns mid-tool-call, the next tool call returns a clear error. No optimistic locking needed.
- **Desktop behavioral semantics deep-dive**: The sandbox server normalizes display interaction. `xdotool`, `xwd`, `ffmpeg` work the same on Xvfb and real X11. Resolution is configured in the VM image, not the tools.
- **`desktop_open_url` page-load semantics, window focus brittleness, clipboard encoding spec**: Implementation details. The agent can inspect results and adapt.
