/**
 * WorkspacePage — 1-on-1 agent workspace.
 *
 * Layout: draggable two-column split.
 *   Left:  Agent screen (interactive VNC) on top, live streaming logs below.
 *   Right: Full conversation thread with message history and input.
 *
 * Agent picker in the top bar. Connection status overlay.
 * Replaces the old chat-only workspace and absorbs CoPilot functionality.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import {
  Monitor,
  MonitorOff,
  ChevronDown,
  GripVertical,
  Eraser,
} from 'lucide-react';

import { AgentStreamProvider, useAgentStreamContext } from '../contexts/AgentStreamContext';
import { useProjectContext } from '../contexts/ProjectContext';
import { AppLayout } from '../components/Layout';
import { VncView } from '../components/ScreenStream';
import { AgentStream } from '../components/AgentChat/AgentStream';
import { MessageList } from '../components/AgentChat/MessageList';
import { MessageInput } from '../components/AgentChat/MessageInput';
import { useAgents, useMessages } from '../hooks';
import { uploadAttachment, listSandboxes } from '../api/client';
import { cn } from '../components/ui';
import type { Agent } from '../types';

// ── Constants ──────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  idle: 'bg-[var(--text-muted)]',
  sleeping: 'bg-[var(--text-muted)]',
  working: 'bg-[var(--color-success)]',
  active: 'bg-[var(--color-success)]',
  busy: 'bg-[var(--color-warning)]',
  error: 'bg-[var(--color-danger)]',
};

const ROLE_BADGE: Record<string, { bg: string; text: string }> = {
  manager: { bg: 'bg-purple-500/15', text: 'text-purple-400' },
  cto: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  engineer: { bg: 'bg-emerald-500/15', text: 'text-emerald-400' },
};

// Draggable split constraints (percentage of container width)
const MIN_LEFT_PCT = 30;
const MAX_LEFT_PCT = 70;
const DEFAULT_LEFT_PCT = 50;

// VNC / Logs vertical split (percentage of left column height)
const MIN_SCREEN_PCT = 25;
const MAX_SCREEN_PCT = 85;
const DEFAULT_SCREEN_PCT = 60;

// ── VNC View Wrapper (resolves orchestrator_sandbox_id) ──────────────────

interface VncViewWrapperProps {
  agentId: string;
  sandboxId: string;
}

function VncViewWrapper({ agentId, sandboxId }: VncViewWrapperProps) {
  const [orchestratorSandboxId, setOrchestratorSandboxId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const resolve = async () => {
      try {
        // The sandbox_id field on agent is the orchestrator_sandbox_id short form
        // Use it directly if available, otherwise fetch sandboxes to find it
        const projectId = new URLSearchParams(window.location.search).get('pid');
        if (!projectId) {
          setOrchestratorSandboxId(sandboxId);
          setLoading(false);
          return;
        }

        // Try to find the sandbox's orchestrator_sandbox_id via listSandboxes
        try {
          const sandboxes = await listSandboxes(projectId);
          const sb = sandboxes.find(s => s.agent_id === agentId);
          if (mounted && sb) {
            setOrchestratorSandboxId(sb.orchestrator_sandbox_id);
          } else if (mounted) {
            // Fallback to the sandbox_id if we can't resolve
            setOrchestratorSandboxId(sandboxId);
          }
        } catch {
          // Fallback: use the sandbox_id directly
          if (mounted) {
            setOrchestratorSandboxId(sandboxId);
          }
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };
    resolve();
    return () => { mounted = false; };
  }, [agentId, sandboxId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-muted)]">
        <span className="text-sm">Connecting…</span>
      </div>
    );
  }

  if (!orchestratorSandboxId) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-muted)]">
        <span className="text-sm">Unable to connect to sandbox</span>
      </div>
    );
  }

  return <VncView sandboxId={orchestratorSandboxId} />;
}

// ── Page Shell ─────────────────────────────────────────────────────────────

export type WorkspaceView = 'workspace' | 'kanban';

interface WorkspacePageProps {
  view?: WorkspaceView;
}

export function WorkspacePage({ view = 'workspace' }: WorkspacePageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const { projects, loading } = useProjectContext();

  if (!projectId) return <Navigate to="/projects" replace />;
  const project = projects.find(p => p.id === projectId);
  if (!loading && !project) return <Navigate to="/projects" replace />;

  // If kanban view requested, lazy-import KanbanBoard to keep this file focused
  if (view === 'kanban') {
    return (
      <AppLayout>
        <AgentStreamProvider projectId={projectId}>
          <KanbanFallback projectId={projectId} />
        </AgentStreamProvider>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <AgentStreamProvider projectId={projectId}>
        <WorkspaceContent projectId={projectId} />
      </AgentStreamProvider>
    </AppLayout>
  );
}

// Kanban kept as a simple wrapper to avoid import-time side effects
function KanbanFallback({ projectId }: { projectId: string }) {
  const [KanbanBoard, setKanbanBoard] = useState<React.ComponentType<{ projectId: string }> | null>(null);
  useEffect(() => {
    import('../components/Kanban').then(m => setKanbanBoard(() => m.KanbanBoard));
  }, []);
  if (!KanbanBoard) return <div className="flex flex-1 items-center justify-center text-[var(--text-muted)]">Loading…</div>;
  return <KanbanBoard projectId={projectId} />;
}

// ── Workspace Content ──────────────────────────────────────────────────────

function WorkspaceContent({ projectId }: { projectId: string }) {
  const { isConnected, workersReady, getBuffer, clearBuffer } = useAgentStreamContext();
  const { agents } = useAgents(projectId);

  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  // Auto-select first agent with sandbox, or first agent
  useEffect(() => {
    if (!selectedAgentId && agents.length > 0) {
      const withSandbox = agents.find(a => a.sandbox_id);
      setSelectedAgentId(withSandbox?.id ?? agents[0].id);
    }
  }, [agents, selectedAgentId]);

  const selectedAgent = agents.find(a => a.id === selectedAgentId);
  const hasSandbox = Boolean(selectedAgent?.sandbox_id);
  const buffer = selectedAgentId
    ? getBuffer(selectedAgentId)
    : { agentId: '', sessionId: null, chunks: [], isStreaming: false, lastActivity: 0 };

  // ── Horizontal split (left: screen+logs | right: conversation) ──────
  const containerRef = useRef<HTMLDivElement>(null);
  const [leftPct, setLeftPct] = useState(DEFAULT_LEFT_PCT);
  const [isDraggingH, setIsDraggingH] = useState(false);

  // ── Vertical split within left column (top: VNC | bottom: logs) ─────
  const leftColRef = useRef<HTMLDivElement>(null);
  const [screenPct, setScreenPct] = useState(DEFAULT_SCREEN_PCT);
  const [isDraggingV, setIsDraggingV] = useState(false);

  // Horizontal drag handlers
  useEffect(() => {
    if (!isDraggingH) return;
    const onMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftPct(Math.min(MAX_LEFT_PCT, Math.max(MIN_LEFT_PCT, pct)));
    };
    const onUp = () => setIsDraggingH(false);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
  }, [isDraggingH]);

  // Vertical drag handlers
  useEffect(() => {
    if (!isDraggingV) return;
    const onMove = (e: MouseEvent) => {
      if (!leftColRef.current) return;
      const rect = leftColRef.current.getBoundingClientRect();
      const pct = ((e.clientY - rect.top) / rect.height) * 100;
      setScreenPct(Math.min(MAX_SCREEN_PCT, Math.max(MIN_SCREEN_PCT, pct)));
    };
    const onUp = () => setIsDraggingV(false);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
  }, [isDraggingV]);

  // Conversation
  const { messages, loading: msgsLoading, error: msgsError, send } = useMessages({
    projectId,
    agentId: selectedAgentId,
  });
  const [uploadError, setUploadError] = useState<string | null>(null);

  const handleSend = useCallback(async (content: string, files?: File[]) => {
    setUploadError(null);
    let attachmentIds: string[] = [];
    if (files && files.length > 0) {
      try {
        const uploads = await Promise.all(files.map(f => uploadAttachment(projectId, f)));
        attachmentIds = uploads.map(a => a.id);
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : 'Upload failed');
        return;
      }
    }
    await send(content, attachmentIds.length > 0 ? attachmentIds : undefined);
  }, [projectId, send]);

  const isDragging = isDraggingH || isDraggingV;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* Connection status */}
      {(!isConnected || !workersReady) && (
        <div className="shrink-0 border-b border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] px-4 py-1.5 text-center text-xs text-[var(--color-warning)]">
          {!isConnected ? 'WebSocket disconnected — reconnecting…' : 'Workers not ready — waiting for backend…'}
        </div>
      )}

      {/* Top bar */}
      <div className="shrink-0 flex items-center gap-3 px-4 py-2.5 border-b border-[var(--border-color)] bg-[var(--surface-card)]">
        <h2 className="text-sm font-semibold text-[var(--text-primary)] whitespace-nowrap">Workspace</h2>
        <AgentPickerDropdown
          agents={agents}
          selectedAgentId={selectedAgentId}
          onSelect={setSelectedAgentId}
        />
        {selectedAgent && (
          <div className="flex items-center gap-2 ml-1">
            <span className={cn('w-2 h-2 rounded-full', STATUS_COLORS[selectedAgent.status] ?? STATUS_COLORS.idle)} />
            <span className="text-xs text-[var(--text-muted)] capitalize">{selectedAgent.status}</span>
            {hasSandbox ? (
              <span className="flex items-center gap-1 text-xs text-[var(--color-success)]">
                <Monitor className="w-3.5 h-3.5" /> Live
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-[var(--text-muted)]">
                <MonitorOff className="w-3.5 h-3.5" /> No sandbox
              </span>
            )}
          </div>
        )}
      </div>

      {/* Main split area */}
      <div
        ref={containerRef}
        className="flex flex-1 min-h-0 relative"
        style={{ cursor: isDragging ? (isDraggingH ? 'col-resize' : 'row-resize') : undefined }}
      >
        {/* ── Left column: Screen + Logs ──────────────────────── */}
        <div
          ref={leftColRef}
          className="flex flex-col min-h-0 min-w-0"
          style={{ width: `${leftPct}%` }}
        >
          {/* VNC Screen */}
          <div className="min-h-0 bg-black relative" style={{ height: `${screenPct}%` }}>
            {hasSandbox && selectedAgent?.sandbox_id ? (
              <VncViewWrapper agentId={selectedAgent.id} sandboxId={selectedAgent.sandbox_id} />
            ) : (
              <div className="flex items-center justify-center h-full text-[var(--text-muted)] gap-2">
                <MonitorOff className="w-6 h-6" />
                <div className="text-center">
                  <p className="text-sm font-medium">
                    {selectedAgent ? 'No sandbox assigned' : 'Select an agent'}
                  </p>
                  <p className="text-xs mt-0.5 text-[var(--text-faint)]">
                    {selectedAgent ? 'Start a sandbox from the Sandbox page' : 'Choose an agent above'}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Vertical drag handle */}
          <div
            className="h-1.5 shrink-0 flex items-center justify-center cursor-row-resize bg-[var(--border-color)] hover:bg-[var(--color-primary)]/30 transition-colors group"
            onMouseDown={e => { e.preventDefault(); setIsDraggingV(true); }}
          >
            <div className="w-8 h-0.5 rounded-full bg-[var(--text-faint)] group-hover:bg-[var(--color-primary)] transition-colors" />
          </div>

          {/* Live Logs */}
          <div className="flex-1 min-h-0 flex flex-col border-t border-[var(--border-color)] bg-[var(--surface-card)]">
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--border-color)] bg-[var(--surface-muted)] shrink-0">
              <h3 className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wide">
                Agent Stream
              </h3>
              {selectedAgentId && (
                <button
                  onClick={() => clearBuffer(selectedAgentId)}
                  className="flex items-center gap-1 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                >
                  <Eraser className="w-3 h-3" /> Clear
                </button>
              )}
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <AgentStream buffer={buffer} compact />
            </div>
          </div>
        </div>

        {/* ── Horizontal drag handle ──────────────────────────── */}
        <div
          className="w-1.5 shrink-0 flex items-center justify-center cursor-col-resize bg-[var(--border-color)] hover:bg-[var(--color-primary)]/30 transition-colors group relative z-10"
          onMouseDown={e => { e.preventDefault(); setIsDraggingH(true); }}
        >
          <GripVertical className="w-3 h-3 text-[var(--text-faint)] group-hover:text-[var(--color-primary)] transition-colors" />
        </div>

        {/* ── Right column: Conversation ──────────────────────── */}
        <div className="flex-1 min-w-0 min-h-0 flex flex-col bg-[var(--app-bg)]">
          {/* Conversation header */}
          <div className="px-4 py-2 border-b border-[var(--border-color)] bg-[var(--surface-card)] shrink-0">
            <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
              Conversation
              {selectedAgent && (
                <span className="normal-case font-normal ml-2 text-[var(--text-faint)]">
                  with {selectedAgent.display_name}
                </span>
              )}
            </h3>
          </div>

          {/* Messages */}
          <div className="flex-1 min-h-0 overflow-hidden border-b border-[var(--border-color)]">
            <MessageList messages={messages} isLoading={msgsLoading} agents={agents} />
          </div>

          {/* Error */}
          {(msgsError || uploadError) && (
            <div className="px-4 py-2 bg-red-500/10 text-sm text-red-400 shrink-0">
              {uploadError ?? msgsError}
            </div>
          )}

          {/* Input */}
          <MessageInput
            onSend={handleSend}
            disabled={!selectedAgentId}
            isStreaming={buffer.isStreaming}
          />
        </div>
      </div>
    </div>
  );
}

// ── Agent Picker Dropdown ──────────────────────────────────────────────────

function AgentPickerDropdown({
  agents,
  selectedAgentId,
  onSelect,
}: {
  agents: Agent[];
  selectedAgentId: string | null;
  onSelect: (agentId: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const selected = agents.find(a => a.id === selectedAgentId);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--surface-hover)] hover:bg-[var(--surface-muted)] border border-[var(--border-color)] text-sm font-medium text-[var(--text-primary)] transition-colors min-w-[200px]"
      >
        {selected ? (
          <>
            <span className={cn('w-2 h-2 rounded-full', STATUS_COLORS[selected.status] ?? STATUS_COLORS.idle)} />
            <span className="truncate">{selected.display_name}</span>
            <span className={cn('text-xs px-1.5 py-0.5 rounded', ROLE_BADGE[selected.role]?.bg, ROLE_BADGE[selected.role]?.text)}>
              {selected.role}
            </span>
          </>
        ) : (
          <span className="text-[var(--text-muted)]">Select an agent…</span>
        )}
        <ChevronDown className="w-4 h-4 ml-auto text-[var(--text-muted)]" />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute left-0 top-full mt-1 z-50 w-64 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] shadow-lg py-1 max-h-80 overflow-y-auto">
            {agents.map(agent => (
              <button
                key={agent.id}
                type="button"
                onClick={() => { onSelect(agent.id); setIsOpen(false); }}
                className={cn(
                  'flex items-center gap-2 w-full px-3 py-2 text-sm text-left hover:bg-[var(--surface-hover)] transition-colors',
                  agent.id === selectedAgentId && 'bg-[var(--color-primary)]/5',
                )}
              >
                <span className={cn('w-2 h-2 rounded-full shrink-0', STATUS_COLORS[agent.status] ?? STATUS_COLORS.idle)} />
                <span className="truncate font-medium text-[var(--text-primary)]">{agent.display_name}</span>
                <span className={cn('text-xs px-1.5 py-0.5 rounded ml-auto shrink-0', ROLE_BADGE[agent.role]?.bg, ROLE_BADGE[agent.role]?.text)}>
                  {agent.role}
                </span>
                {agent.sandbox_id && <Monitor className="w-3 h-3 shrink-0 text-[var(--color-success)]" />}
              </button>
            ))}
            {agents.length === 0 && (
              <p className="px-3 py-4 text-xs text-[var(--text-muted)] text-center">No agents in this project</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default WorkspacePage;
