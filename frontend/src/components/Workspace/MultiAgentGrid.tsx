/**
 * MultiAgentGrid — 2×2 grid for monitoring up to 4 agents simultaneously.
 * Each cell shows VNC + scrollable log sidebar.
 * Adapts grid layout: 1 agent = full width, 2 = side by side, 3-4 = 2×2.
 */

import type { Agent, AgentStreamBuffer } from '../../types';
import { AgentGridCell } from './AgentGridCell';
import { cn } from '../ui';

interface MultiAgentGridProps {
  agents: Agent[];
  selectedIds: string[];
  getBuffer: (agentId: string) => AgentStreamBuffer;
  onExpand: (agentId: string) => void;
  onClearBuffer: (agentId: string) => void;
}

export function MultiAgentGrid({
  agents,
  selectedIds,
  getBuffer,
  onExpand,
  onClearBuffer,
}: MultiAgentGridProps) {
  const selectedAgents = selectedIds
    .map((id) => agents.find((a) => a.id === id))
    .filter(Boolean) as Agent[];

  if (selectedAgents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-muted)] text-sm">
        Select agents from the list above to monitor them
      </div>
    );
  }

  const gridClass = cn(
    'grid gap-2 h-full min-h-0 p-2',
    selectedAgents.length === 1 && 'grid-cols-1',
    selectedAgents.length === 2 && 'grid-cols-2',
    selectedAgents.length >= 3 && 'grid-cols-2 grid-rows-2'
  );

  return (
    <div className={gridClass}>
      {selectedAgents.map((agent) => (
        <AgentGridCell
          key={agent.id}
          agent={agent}
          buffer={getBuffer(agent.id)}
          onExpand={onExpand}
          onClearBuffer={onClearBuffer}
        />
      ))}
    </div>
  );
}

export default MultiAgentGrid;
