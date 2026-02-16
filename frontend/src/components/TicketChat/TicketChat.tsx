/**
 * TicketChat Component
 * Chat UI for a single ticket (engineer question / user reply).
 */

import { useCallback, useRef, useEffect, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useTicketChat } from '../../hooks/useTicketChat';
import { MarkdownContent } from '../MarkdownContent';
import type { TicketMessage } from '../../types';

interface TicketChatProps {
  ticketId: string;
  projectId: string;
  agentName: string;
  taskTitle: string;
  onClose: () => void;
}

function formatTime(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function MessageBubble({ message }: { message: TicketMessage }) {
  const isUser = message.from_user_id != null || message.from_agent_id == null;

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`flex items-end gap-2 max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium flex-shrink-0 ${
            isUser ? 'bg-blue-500' : 'bg-emerald-500'
          }`}
        >
          {isUser ? 'You' : 'EN'}
        </div>
        <div
          className={`rounded-2xl px-4 py-2 ${
            isUser ? 'bg-blue-500 text-white rounded-br-sm' : 'bg-gray-100 text-gray-900 rounded-bl-sm'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <MarkdownContent>{message.content}</MarkdownContent>
          )}
          <p className={`text-xs mt-1 ${isUser ? 'text-blue-100' : 'text-gray-500'}`}>
            {formatTime(message.created_at)}
          </p>
        </div>
      </div>
    </div>
  );
}

export function TicketChat({ ticketId, projectId, agentName, taskTitle, onClose: _onClose }: TicketChatProps) {
  const { messages, isLoading, sendReply } = useTicketChat(ticketId, projectId);
  const [content, setContent] = useState('');
  const [isSending, setIsSending] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      const trimmedContent = content.trim();
      if (!trimmedContent || isSending) return;
      setIsSending(true);
      try {
        await sendReply(trimmedContent);
        setContent('');
      } catch (err) {
        console.error('Failed to send reply:', err);
      } finally {
        setIsSending(false);
      }
    },
    [content, isSending, sendReply]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-gray-200 bg-gray-50 text-sm text-gray-700">
        <span className="font-medium">{agentName}</span> needs help with: <span className="italic">{taskTitle}</span>
      </div>

      <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="text-sm text-gray-500">Loading...</div>
        ) : (
          messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-gray-200 bg-white p-3">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your reply... (Enter to send)"
            disabled={isSending}
            rows={1}
            className="flex-1 px-3 py-2 rounded-lg border border-gray-300 focus:border-blue-500 focus:ring-1 focus:ring-blue-200 outline-none resize-none text-sm disabled:bg-gray-100"
            style={{ minHeight: '40px', maxHeight: '100px' }}
          />
          <button
            type="submit"
            disabled={isSending || !content.trim()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg text-sm font-medium hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}

export default TicketChat;
