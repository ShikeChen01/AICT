/**
 * CoPilotPage — full-screen co-pilot mode for working alongside a single agent.
 * Left: Large VNC desktop view (agent sandbox).
 * Right: Agent stream logs + chat input for direct messaging.
 * Promoted from ExpandedAgentModal to a dedicated top-level page.
 */

import { useCallback, useEffect, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { Monitor, MonitorOff, Send, ChevronDown } from 'lucide-react';
import { AgentStreamProvider, useAgentStreamContext } from '../contexts/AgentStreamContext';
import { useProjectContext } from '../contexts/ProjectContext';
import { AppLayout } from '../components/Layout';
import { AgentStream } from '../components/AgentChat/AgentStream';
import { VncView } from '../components/ScreenStream';
import { useAgents, useMessages } from '../hooks';
import { listSandboxes } from '../api/client';
import { cn } from '../components/ui';
import type { Agent, Sandbox } from '../types';

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
  const selected = agents.find((a) => a.id === selectedAgentId);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--surface-hover)] hover:bg-[var(--surface-muted)] border border-[var(--border-color)] text-sm font-medium text-[var(--text-primary)] transition-colors min-w-[200px]"
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
            {agents.map((agent) => (
              <button
                key={agent.id}
                type="button"
                onClick={() => {
                  onSelect(agent.id);
                  setIsOpen(false);
                }}
                className={cn(
                  'flex items-center gap-2 w-full px-3 py-2 text-sm text-left hover:bg-[var(--surface-hover)] transition-colors',
                  agent.id === selectedAgentId && 'bg-[var(--color-primary)]/5'
                )}
              >
                <span className={cn('w-2 h-2 rounded-full shrink-0', STATUS_COLORS[agent.status] ?? STATUS_COLORS.idle)} />
                <span className="truncate font-medium text-[var(--text-primary)]">{agent.display_name}</span>
                <span className={cn('text-xs px-1.5 py-0.5 rounded ml-auto shrink-0', ROLE_BADGE[agent.role]?.bg, ROLE_BADGE[agent.role]?.text)}>
                  {agent.role}
                </span>
                {agent.sandbox_id && (
                  <Monitor className="w-3 h-3 shrink-0 text-[var(--color-success)]" />
                )}
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

function ChatInput({
  projectId,
  agentId,
}: {
  projectId: string;
  agentId: string | null;
}) {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const { send } = useMessages({ projectId, agentId });

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || !agentId) return;
    setSending(true);
    try {
      await send(text);
      setInput('');
    } catch {
      // error handling done by useMessages
    } finally {
      setSending(false);
    }
  }, [input, agentId, send]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex items-center gap-2 p-3 border-t border-[var(--border-color)] bg-[var(--surface-card)]">
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={agentId ? 'Message this agent…' : 'Select an agent first'}
        disabled={!agentId || sending}
        className="flex-1 rounded-lg border border-[var(--border-color)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/30 disabled:opacity-50"
      />
      <button
        type="button"
        onClick={handleSend}
        disabled={!agentId || !input.trim() || sending}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] disabled:opacity-40 transition-colors"
      >
        <Send className="w-4 h-4" />
      </button>
    </div>
  );
}

function CoPilotContent({ projectId }: { projectId: string }) {
  const {
    isConnected,
    workersReady,
    getBuffer,
    clearBuffer,
  } = useAgentStreamContext();

  const { agents } = useAgents(projectId);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  // Auto-select first agent with a sandbox, or first agent
  useEffect(() => {
    if (!selectedAgentId && agents.length > 0) {
      const withSandbox = agents.find((a) => a.sandbox_id);
      setSelectedAgentId(withSandbox?.id ?? agents[0].id); // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, [agents, selectedAgentId]);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);
  const hasSandbox = Boolean(selectedAgent?.sandbox_id);
  const buffer = selectedAgentId ? getBuffer(selectedAgentId) : { agentId: '', sessionId: null, chunks: [], isStreaming: false, lastActivity: 0 };

  // Resolve orchestrator_sandbox_id for VNC connection
  const [sandboxMap, setSandboxMap] = useState<Record<string, string>>({});
  useEffect(() => {
    listSandboxes(projectId)
      .then((sbs: Sandbox[]) => {
        const map: Record<string, string> = {};
        for (const sb of sbs) {
          if (sb.agent_id) map[sb.agent_id] = sb.orchestrator_sandbox_id;
        }
        setSandboxMap(map);
      })
      .catch(() => {});
  }, [projectId]);
  const resolvedSandboxId = selectedAgent ? (sandboxMap[selectedAgent.id] ?? selectedAgent.sandbox_id) : null;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* Connection status */}
      {(!isConnected || !workersReady) && (
        <div className="shrink-0 border-b border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] px-4 py-1.5 text-center text-xs text-[var(--color-warning)]">
          {!isConnected ? 'WebSocket disconnected — reconnecting…' : 'Workers not ready — waiting for backend…'}
        </div>
      )}

      {/* Top bar: agent picker + status */}
      <div className="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-[var(--border-color)] bg-[var(--surface-card)]">
        <h2 className="text-sm font-semibold text-[var(--text-primary)] whitespace-nowrap">Co-Pilot</h2>
        <AgentPickerDropdown
          agents={agents}
          selectedAgentId={selectedAgentId}
          onSelect={setSelectedAgentId}
        />
        {selectedAgent && (
          <div className="flex items-center gap-2 ml-2">
            <span className={cn('w-2.5 h-2.5 rounded-full', STATUS_COLORS[selectedAgent.status] ?? STATUS_COLORS.idle)} />
            <span className="text-xs text-[var(--text-muted)]">{selectedAgent.status}</span>
            {hasSandbox ? (
              <span className="flex items-center gap-1 text-xs text-[var(--color-success)]">
                <Monitor className="w-3.5 h-3.5" />
                Sandbox active
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-[var(--text-muted)]">
                <MonitorOff className="w-3.5 h-3.5" />
                No sandbox
              </span>
            )}
          </div>
        )}
      </div>

      {/* Main body: VNC left + Logs right */}
      <div className="flex flex-1 min-h-0">
        {/* VNC View (left - main area) */}
        <div className="flex-1 min-w-0 min-h-0 bg-[var(--surface-muted)]">
          {hasSandbox && selectedAgent && resolvedSandboxId ? (
            <VncView sandboxId={resolvedSandboxId} />
          ) : (
            <div className="flex items-center justify-center h-full text-[var(--text-muted)] gap-3">
              <MonitorOff className="w-8 h-8" />
              <div className="text-center">
                <p className="text-base font-medium">
                  {selectedAgent ? 'No sandbox assigned' : 'Select an agent to begin'}
                </p>
                <p className="text-sm mt-1 text-[var(--text-muted)]">
                  {selectedAgent
                    ? 'Start a sandbox from Agent Build or Project Settings to see the agent\'s desktop'
                    : 'Choose an agent from the dropdown above'}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Logs sidebar (right) */}
        <div className="w-[400px] shrink-0 flex flex-col min-h-0 border-l border-[var(--border-color)] bg-[var(--surface-card)]">
          <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--border-color)] bg-[var(--surface-muted)] shrink-0">
            <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
              Agent Stream
            </h3>
            {selectedAgentId && (
              <button
                type="button"
                onClick={() => clearBuffer(selectedAgentId)}
                className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
              >
                Clear
              </button>
            )}
          </div>

          {/* Stream output */}
          <div className="flex-1 min-h-0 overflow-hidden">
            <AgentStream buffer={buffer} />
          </div>

          {/* Chat input */}
          <ChatInput projectId={projectId} agentId={selectedAgentId} />
        </div>
      </div>
    </div>
  );
}

export function CoPilotPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { projects, loading } = useProjectContext();

  if (!projectId) {
    return <Navigate to="/projects" replace />;
  }

  const project = projects.find((p) => p.id === projectId);
  if (!loading && !project) {
    return <Navigate to="/projects" replace />;
  }

  return (
    <AppLayout>
      <AgentStreamProvider projectId={projectId}>
        <CoPilotContent projectId={projectId} />
      </AgentStreamProvider>
    </AppLayout>
  );
}

export default CoPilotPage;
