/**
 * AgentSelector — compact agent list for multi-agent grid selection.
 * Click to toggle selection (max 4 agents). Selected agents highlighted.
 */

import { CheckSquare, Square, Monitor } from 'lucide-react';
import type { Agent } from '../../types';
import { cn } from '../ui';

const MAX_SELECTED = 4;

const STATUS_DOT: Record<string, string> = {
  idle: 'bg-[var(--text-muted)]',
  working: 'bg-[var(--color-success)]',
  error: 'bg-[var(--color-danger)]',
  paused: 'bg-[var(--color-warning)]',
};

interface AgentSelectorProps {
  agents: Agent[];
  selectedIds: string[];
  onToggle: (agentId: string) => void;
}

export function AgentSelector({ agents, selectedIds, onToggle }: AgentSelectorProps) {
  const selectedSet = new Set(selectedIds);

  return (
    <div className="flex flex-col gap-1 p-2">
      <div className="flex items-center justify-between px-2 pb-1">
        <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
          Monitor Agents
        </h4>
        <span className="text-xs text-[var(--text-muted)] font-mono">
          {selectedIds.length}/{MAX_SELECTED}
        </span>
      </div>
      {agents.map((agent) => {
        const isSelected = selectedSet.has(agent.id);
        const isDisabled = !isSelected && selectedIds.length >= MAX_SELECTED;

        return (
          <button
            key={agent.id}
            type="button"
            onClick={() => !isDisabled && onToggle(agent.id)}
            disabled={isDisabled}
            className={cn(
              'flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left text-sm transition-colors w-full',
              isSelected
                ? 'bg-[var(--color-primary-light)] text-[var(--color-primary)] border border-[var(--color-primary)]/20'
                : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] border border-transparent',
              isDisabled && 'opacity-40 cursor-not-allowed'
            )}
          >
            {isSelected ? (
              <CheckSquare className="w-3.5 h-3.5 flex-shrink-0" />
            ) : (
              <Square className="w-3.5 h-3.5 flex-shrink-0" />
            )}
            <span className={cn('w-2 h-2 rounded-full flex-shrink-0', STATUS_DOT[agent.status] ?? STATUS_DOT.idle)} />
            <span className="truncate font-medium">{agent.display_name}</span>
            <span className="text-xs opacity-60 ml-auto flex-shrink-0">{agent.role}</span>
            {agent.sandbox_id && (
              <Monitor className="w-3 h-3 flex-shrink-0 text-[var(--color-success)]" aria-label="Has sandbox" />
            )}
          </button>
        );
      })}
      {agents.length === 0 && (
        <p className="text-xs text-[var(--text-muted)] px-2 py-4 text-center">No agents in this project</p>
      )}
    </div>
  );
}

export default AgentSelector;
