/**
 * AgentSelector — pick which agent to talk to.
 */

import type { Agent } from '../../types';
import { Select } from '../ui';

interface AgentSelectorProps {
  agents: Agent[];
  selectedAgentId: string | null;
  onSelect: (agentId: string) => void;
  disabled?: boolean;
}

export function AgentSelector({
  agents,
  selectedAgentId,
  onSelect,
  disabled,
}: AgentSelectorProps) {
  if (agents.length === 0) {
    return (
      <div className="px-4 py-3 text-sm text-gray-500">
        No agents in this project.
      </div>
    );
  }

  return (
    <div className="border-b border-[var(--border-color)] bg-[var(--surface-muted)] px-4 py-3">
      <label htmlFor="agent-selector" className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
        Talk to
      </label>
      <Select
        id="agent-selector"
        value={selectedAgentId ?? ''}
        onChange={(e) => onSelect(e.target.value)}
        disabled={disabled}
        className="border-[var(--border-color)] bg-[var(--surface-card)]"
      >
        {agents.map((agent) => (
          <option key={agent.id} value={agent.id}>
            {agent.display_name} ({agent.role})
          </option>
        ))}
      </Select>
    </div>
  );
}

export default AgentSelector;
