/**
 * MessageList — displays channel messages (user ↔ agent conversation).
 */

import { useMemo } from 'react';
import { MarkdownContent } from '../MarkdownContent';
import type { Agent, AgentRole, ChannelMessage } from '../../types';
import { Button } from '../ui';
import { useAutoFollow } from '../../hooks';

const USER_AGENT_ID = '00000000-0000-0000-0000-000000000000';

const ROLE_ABBREVIATION: Record<AgentRole, string> = {
  manager: 'GM',
  cto: 'CTO',
  engineer: 'ENG',
};

const ROLE_COLOR: Record<AgentRole, string> = {
  manager: 'bg-purple-500',
  cto: 'bg-cyan-500',
  engineer: 'bg-green-500',
};

interface MessageListProps {
  messages: ChannelMessage[];
  isLoading?: boolean;
  /** Optional: from_agent_id that represents "user" (default USER_AGENT_ID). */
  userAgentId?: string | null;
  /** Optional: agents list used to show role labels in message bubbles. */
  agents?: Agent[];
}

function formatTime(dateString: string): string {
  return new Date(dateString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function MessageBubble({
  message,
  isUser,
  agentLabel,
  agentColorClass,
}: {
  message: ChannelMessage;
  isUser: boolean;
  agentLabel: string;
  agentColorClass: string;
}) {
  const isUnread = !isUser && message.status !== 'read';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`flex items-end gap-2 max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <div className="relative flex-shrink-0">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-medium ${
              isUser ? 'bg-blue-500' : agentColorClass
            }`}
          >
            {isUser ? 'You' : agentLabel}
          </div>
          {isUnread && (
            <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-blue-500 rounded-full border border-white" />
          )}
        </div>
        <div
          className={`rounded-2xl px-4 py-2 ${
            isUser
              ? 'bg-blue-500 text-white rounded-br-sm'
              : 'bg-gray-100 text-gray-900 rounded-bl-sm'
          }`}
        >
          {!isUser ? (
            <MarkdownContent>{message.content}</MarkdownContent>
          ) : (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          )}
          <p className={`text-xs mt-1 ${isUser ? 'text-blue-100' : 'text-gray-500'}`}>
            {formatTime(message.created_at)}
          </p>
        </div>
      </div>
    </div>
  );
}

export function MessageList({ messages, isLoading, userAgentId, agents }: MessageListProps) {
  const uid = userAgentId ?? USER_AGENT_ID;

  const agentMap = useMemo(() => {
    const map = new Map<string, Agent>();
    for (const agent of agents ?? []) {
      map.set(agent.id, agent);
    }
    return map;
  }, [agents]);

  const messageKey = useMemo(
    () => `${messages.length}:${messages[messages.length - 1]?.id ?? 'none'}`,
    [messages]
  );
  const { attachRef, onScroll, isAutoFollow, jumpToLatest } = useAutoFollow<HTMLDivElement>({
    dependencyKey: messageKey,
  });

  return (
    <div className="relative flex-1 min-h-0">
      {!isAutoFollow && messages.length > 0 && (
        <div className="absolute bottom-3 right-3 z-10">
          <Button size="sm" onClick={jumpToLatest}>
            Jump to latest
          </Button>
        </div>
      )}
      <div ref={attachRef} onScroll={onScroll} className="h-full overflow-y-auto p-4 space-y-1">
        {isLoading && (
          <div className="flex justify-start mb-4">
            <div className="flex items-end gap-2">
              <div className="w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center text-white text-xs">
                ...
              </div>
              <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-3">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          </div>
        )}
        {messages.map((msg) => {
          const isUser = msg.from_agent_id === null || msg.from_agent_id === uid;
          const agent = msg.from_agent_id ? agentMap.get(msg.from_agent_id) : undefined;
          const agentLabel = agent ? ROLE_ABBREVIATION[agent.role] : 'A';
          const agentColorClass = agent ? ROLE_COLOR[agent.role] : 'bg-purple-500';
          return (
            <MessageBubble
              key={msg.id}
              message={msg}
              isUser={isUser}
              agentLabel={agentLabel}
              agentColorClass={agentColorClass}
            />
          );
        })}
      </div>
    </div>
  );
}

export default MessageList;
