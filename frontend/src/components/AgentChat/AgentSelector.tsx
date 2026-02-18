/**
 * AgentSelector — pick which agent to talk to.
 */

import type { Agent } from '../../types';

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
      <div className="px-4 py-2 text-sm text-gray-500">
        No agents in this project.
      </div>
    );
  }

  return (
    <div className="border-b border-gray-200 bg-white px-4 py-3">
      <label htmlFor="agent-selector" className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
        Talk to
      </label>
      <select
        id="agent-selector"
        value={selectedAgentId ?? ''}
        onChange={(e) => onSelect(e.target.value)}
        disabled={disabled}
        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none disabled:bg-gray-100"
      >
        {agents.map((agent) => (
          <option key={agent.id} value={agent.id}>
            {agent.display_name} ({agent.role})
          </option>
        ))}
      </select>
    </div>
  );
}

export default AgentSelector;
