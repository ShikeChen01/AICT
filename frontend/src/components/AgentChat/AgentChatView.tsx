/**
 * AgentChatView — conversation with an agent: stream + message history + input.
 */

import { useCallback, useEffect } from 'react';
import { AgentSelector } from './AgentSelector';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { AgentStream } from './AgentStream';
import { useMessages, useAgentStream, useAgents } from '../../hooks';

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
  const { buffer, isStreaming, clearBuffer } = useAgentStream(selectedAgentId);

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
    <div className="flex flex-col h-full bg-white rounded-lg border border-gray-200 overflow-hidden">
      <AgentSelector
        agents={agents}
        selectedAgentId={effectiveAgentId}
        onSelect={onSelectAgent}
        disabled={loading}
      />

      <div className="flex-1 flex flex-col min-h-0">
        {/* Message history (from API) */}
        <div className="flex-1 min-h-0 flex flex-col border-b border-gray-100">
          <MessageList messages={messages} isLoading={loading} />
        </div>

        {/* Live stream buffer */}
        <div className="flex-shrink-0 border-b border-gray-100" style={{ maxHeight: '40%' }}>
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide px-4 py-2 bg-gray-50 border-b border-gray-100">
            Live stream
          </div>
          <AgentStream buffer={buffer} onClear={clearBuffer} />
        </div>

        {error && (
          <div className="px-4 py-2 bg-red-50 text-red-700 text-sm">
            {error}
          </div>
        )}

        <MessageInput
          onSend={handleSend}
          disabled={!effectiveAgentId}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
}

export default AgentChatView;
