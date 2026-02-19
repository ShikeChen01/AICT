/**
 * MessageList — displays channel messages (user ↔ agent conversation).
 */

import { useMemo } from 'react';
import { MarkdownContent } from '../MarkdownContent';
import type { ChannelMessage } from '../../types';
import { Button } from '../ui';
import { useAutoFollow } from '../../hooks';

const USER_AGENT_ID = '00000000-0000-0000-0000-000000000000';

interface MessageListProps {
  messages: ChannelMessage[];
  isLoading?: boolean;
  /** Optional: from_agent_id that represents "user" (default USER_AGENT_ID). */
  userAgentId?: string | null;
}

function formatTime(dateString: string): string {
  return new Date(dateString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function MessageBubble({
  message,
  isUser,
}: {
  message: ChannelMessage;
  isUser: boolean;
}) {
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`flex items-end gap-2 max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium flex-shrink-0 ${
            isUser ? 'bg-blue-500' : 'bg-purple-500'
          }`}
        >
          {isUser ? 'You' : 'A'}
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

export function MessageList({ messages, isLoading, userAgentId }: MessageListProps) {
  const uid = userAgentId ?? USER_AGENT_ID;
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
              <div className="w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center text-white text-sm">
                A
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
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isUser={msg.from_agent_id === null || msg.from_agent_id === uid}
          />
        ))}
      </div>
    </div>
  );
}

export default MessageList;
