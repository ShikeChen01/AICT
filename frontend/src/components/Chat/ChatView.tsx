/**
 * ChatView Component
 * Main chat interface for user-GM communication
 */

import { useCallback } from 'react';
import { useChat } from '../../hooks';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';

interface ChatViewProps {
  projectId: string;
}

export function ChatView({ projectId }: ChatViewProps) {
  const { messages, isLoading, isSending, gmStatus, isAwaitingGmReply, error, sendMessage } =
    useChat(projectId);

  const handleSend = useCallback(
    async (content: string) => {
      await sendMessage(content);
    },
    [sendMessage]
  );

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4">
        <div className="w-10 h-10 rounded-full bg-purple-500 flex items-center justify-center text-white font-bold">
          GM
        </div>
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Chat with GM</h1>
          <div className="flex items-center gap-2 text-sm">
            <div
              className={`w-2 h-2 rounded-full ${
                gmStatus === 'available' ? 'bg-green-500' : 'bg-amber-500 animate-pulse'
              }`}
            />
            <span className="text-gray-500">
              {gmStatus === 'available'
                ? 'Available'
                : isAwaitingGmReply
                  ? 'Waking up...'
                  : 'Processing...'}
            </span>
          </div>
          {gmStatus === 'busy' && isAwaitingGmReply && (
            <p className="text-xs text-amber-600 mt-1">GM is waking up and processing your request.</p>
          )}
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border-b border-red-200 px-6 py-3 text-red-700 text-sm">
          <strong>Error:</strong> {error.message}
        </div>
      )}

      {/* Loading state */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-gray-500">
            <svg
              className="animate-spin h-8 w-8 mx-auto mb-4 text-blue-500"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
                fill="none"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <p>Loading chat history...</p>
          </div>
        </div>
      ) : (
        <MessageList messages={messages} isLoading={isSending} />
      )}

      {/* Input */}
      <MessageInput onSend={handleSend} disabled={isLoading} gmStatus={gmStatus} />
    </div>
  );
}

export default ChatView;
