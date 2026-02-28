/**
 * AgentChatView — conversation with an agent: stream + message history + input.
 */

import { useCallback, useEffect, useState } from 'react';
import { AgentSelector } from './AgentSelector';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { useMessages, useAgentStream, useAgents } from '../../hooks';
import { Panel } from '../ui';
import { uploadAttachment } from '../../api/client';

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
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedAgentId && agents.length > 0) {
      onSelectAgent(agents[0].id);
    }
  }, [agents, selectedAgentId, onSelectAgent]);

  const handleSend = useCallback(
    async (content: string, files?: File[]) => {
      setUploadError(null);
      let attachmentIds: string[] = [];

      // Upload images first, collect their IDs
      if (files && files.length > 0) {
        try {
          const uploads = await Promise.all(
            files.map((file) => uploadAttachment(projectId, file))
          );
          attachmentIds = uploads.map((a) => a.id);
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'Upload failed';
          setUploadError(msg);
          return;
        }
      }

      await send(content, attachmentIds.length > 0 ? attachmentIds : undefined);
    },
    [projectId, send]
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

        {(error || uploadError) && (
          <div className="px-4 py-2 bg-red-50 text-sm text-red-700">
            {uploadError ?? error}
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
