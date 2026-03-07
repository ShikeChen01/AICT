/**
 * AgentGridCell — single cell in the multi-agent monitoring grid.
 * Shows agent header with status, VNC view (or placeholder), and scrollable log sidebar.
 */

import { Maximize2, Monitor, MonitorOff } from 'lucide-react';
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

const ROLE_COLORS: Record<string, string> = {
  manager: 'text-[var(--color-manager)]',
  cto: 'text-[var(--color-cto)]',
  engineer: 'text-[var(--color-engineer)]',
};

interface AgentGridCellProps {
  agent: Agent;
  buffer: AgentStreamBuffer;
  onExpand: (agentId: string) => void;
  onClearBuffer: (agentId: string) => void;
}

export function AgentGridCell({ agent, buffer, onExpand, onClearBuffer }: AgentGridCellProps) {
  const hasSandbox = Boolean(agent.sandbox_id);

  return (
    <div className="flex flex-col min-h-0 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] overflow-hidden shadow-[var(--shadow-xs)]">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--border-color)] bg-[var(--surface-muted)] shrink-0">
        <span className={cn('w-2 h-2 rounded-full flex-shrink-0', STATUS_COLORS[agent.status] ?? STATUS_COLORS.idle)} />
        <span className="text-sm font-semibold text-[var(--text-primary)] truncate">{agent.display_name}</span>
        <span className={cn('text-xs font-medium flex-shrink-0', ROLE_COLORS[agent.role] ?? 'text-[var(--text-muted)]')}>
          {agent.role}
        </span>
        <div className="ml-auto flex items-center gap-1">
          {hasSandbox ? (
            <Monitor className="w-3.5 h-3.5 text-[var(--color-success)]" title="Sandbox active" />
          ) : (
            <MonitorOff className="w-3.5 h-3.5 text-[var(--text-muted)]" title="No sandbox" />
          )}
          <button
            type="button"
            onClick={() => onExpand(agent.id)}
            className="flex h-6 w-6 items-center justify-center rounded text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] transition-colors"
            title="Expand to full screen"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Content: VNC top, Logs bottom */}
      <div className="flex flex-col flex-1 min-h-0">
        {/* VNC / Screen section */}
        <div className="flex-1 min-h-0 border-b border-[var(--border-color)]">
          {hasSandbox ? (
            <VncView sandboxId={agent.sandbox_id} />
          ) : (
            <div className="flex items-center justify-center h-full text-[var(--text-muted)] text-xs gap-1.5 bg-[var(--surface-muted)]">
              <MonitorOff className="w-4 h-4" />
              <span>No sandbox assigned</span>
            </div>
          )}
        </div>

        {/* Log sidebar (scrollable, takes ~40% height) */}
        <div className="flex flex-col" style={{ flex: '0 0 40%', minHeight: 0 }}>
          <div className="flex items-center justify-between px-2 py-1 border-b border-[var(--border-color-subtle)] bg-[var(--surface-muted)]">
            <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wide">
              Live Log
            </span>
            <button
              type="button"
              onClick={() => onClearBuffer(agent.id)}
              className="text-[10px] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              Clear
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <AgentStream buffer={buffer} compact />
          </div>
        </div>
      </div>
    </div>
  );
}

export default AgentGridCell;
