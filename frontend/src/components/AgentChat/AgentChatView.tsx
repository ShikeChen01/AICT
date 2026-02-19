/**
 * AgentChatView — conversation with an agent: stream + message history + input.
 */

import { useCallback, useEffect } from 'react';
import { AgentSelector } from './AgentSelector';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { useMessages, useAgentStream, useAgents } from '../../hooks';
import { Panel } from '../ui';

interface AgentChatViewProps {
  projectId: string;
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string) => void;
}

export function AgentChatView({
  projectId,
  selectedAgentId,
  onSelectAgent,
}: AgentChatViewProps) {
  const { agents } = useAgents(projectId);
  const { messages, loading, error, send } = useMessages({
    projectId,
    agentId: selectedAgentId,
  });
  const { isStreaming } = useAgentStream(selectedAgentId);

  useEffect(() => {
    if (!selectedAgentId && agents.length > 0) {
      onSelectAgent(agents[0].id);
    }
  }, [agents, selectedAgentId, onSelectAgent]);

  const handleSend = useCallback(
    async (content: string) => {
      await send(content);
    },
    [send]
  );

  const effectiveAgentId = selectedAgentId ?? (agents[0]?.id ?? null);

  return (
    <Panel
      title="Conversation"
      subtitle="Ask, assign, and monitor agent responses in realtime"
      className="h-full"
      bodyClassName="flex min-h-0 flex-col"
    >
      <AgentSelector
        agents={agents}
        selectedAgentId={effectiveAgentId}
        onSelect={onSelectAgent}
        disabled={loading}
      />

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex min-h-0 flex-1 flex-col border-b border-[var(--border-color)]">
          <MessageList messages={messages} isLoading={loading} agents={agents} />
        </div>

        {error && (
          <div className="px-4 py-2 bg-red-50 text-sm text-red-700">
            {error}
          </div>
        )}

        <MessageInput
          onSend={handleSend}
          disabled={!effectiveAgentId}
          isStreaming={isStreaming}
        />
      </div>
    </Panel>
  );
}

export default AgentChatView;
