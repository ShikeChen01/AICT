/**
 * ExpandedAgentModal — full-screen co-pilot mode for a single agent.
 * Left: large VNC view. Right sidebar: full AgentStream logs.
 * Close with button or Escape key.
 * Future: add conversation bar for Sandbox Co-Pilot interaction.
 */

import { useEffect, useCallback } from 'react';
import { X, Maximize2, Monitor, MonitorOff } from 'lucide-react';
import type { Agent, AgentStreamBuffer } from '../../types';
import { AgentStream } from '../AgentChat/AgentStream';
import { VncView } from '../ScreenStream';
import { cn } from '../ui';

const STATUS_COLORS: Record<string, string> = {
  idle: 'bg-[var(--text-muted)]',
  working: 'bg-[var(--color-success)]',
  error: 'bg-[var(--color-danger)]',
  paused: 'bg-[var(--color-warning)]',
};

interface ExpandedAgentModalProps {
  agent: Agent;
  buffer: AgentStreamBuffer;
  onClose: () => void;
  onClearBuffer: (agentId: string) => void;
}

export function ExpandedAgentModal({
  agent,
  buffer,
  onClose,
  onClearBuffer,
}: ExpandedAgentModalProps) {
  const hasSandbox = Boolean(agent.sandbox_id);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[var(--app-bg)]">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border-color)] bg-[var(--surface-card)] shrink-0">
        <Maximize2 className="w-4 h-4 text-[var(--color-primary)]" />
        <span className={cn('w-2.5 h-2.5 rounded-full', STATUS_COLORS[agent.status] ?? STATUS_COLORS.idle)} />
        <h2 className="text-base font-semibold text-[var(--text-primary)]">{agent.display_name}</h2>
        <span className="text-sm text-[var(--text-muted)]">{agent.role}</span>
        {hasSandbox && (
          <span className="flex items-center gap-1 text-xs text-[var(--color-success)]">
            <Monitor className="w-3.5 h-3.5" />
            Sandbox active
          </span>
        )}
        <span className="text-xs text-[var(--text-muted)] ml-auto mr-2">
          Press Escape to close
        </span>
        <button
          type="button"
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] transition-colors"
          title="Close expanded view"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Body: VNC left, Logs right */}
      <div className="flex flex-1 min-h-0">
        {/* VNC View */}
        <div className="flex-1 min-w-0">
          {hasSandbox ? (
            <VncView sandboxId={agent.sandbox_id} />
          ) : (
            <div className="flex items-center justify-center h-full text-[var(--text-muted)] gap-2 bg-[var(--surface-muted)]">
              <MonitorOff className="w-6 h-6" />
              <div className="text-center">
                <p className="text-sm font-medium">No sandbox assigned</p>
                <p className="text-xs mt-1">Start a sandbox from the workspace to see the agent's desktop</p>
              </div>
            </div>
          )}
        </div>

        {/* Log Sidebar */}
        <div className="w-96 flex-shrink-0 flex flex-col border-l border-[var(--border-color)] bg-[var(--surface-card)]">
          <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--border-color)] bg-[var(--surface-muted)]">
            <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
              Agent Log
            </h3>
            <button
              type="button"
              onClick={() => onClearBuffer(agent.id)}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              Clear
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <AgentStream buffer={buffer} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default ExpandedAgentModal;
