/**
 * MessageInput — user message composer for agent chat.
 */

import { useState, useCallback, type FormEvent, type KeyboardEvent } from 'react';

interface MessageInputProps {
  onSend: (content: string) => Promise<unknown>;
  disabled?: boolean;
  isStreaming?: boolean;
}

export function MessageInput({ onSend, disabled, isStreaming }: MessageInputProps) {
  const [content, setContent] = useState('');
  const [isSending, setIsSending] = useState(false);

  const handleSubmit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      const trimmed = content.trim();
      if (!trimmed || isSending || disabled) return;
      setIsSending(true);
      try {
        await onSend(trimmed);
        setContent('');
      } catch (err) {
        console.error('Failed to send message:', err);
      } finally {
        setIsSending(false);
      }
    },
    [content, isSending, disabled, onSend]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void handleSubmit();
      }
    },
    [handleSubmit]
  );

  const isDisabled = disabled || isSending;

  return (
    <div className="border-t border-gray-200 bg-white p-4">
      {isStreaming && (
        <div className="flex items-center gap-2 text-sm text-amber-600 mb-2">
          <div className="w-2 h-2 bg-amber-500 rounded-full animate-pulse" />
          Agent is responding...
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
          disabled={isDisabled}
          rows={1}
          className="flex-1 px-4 py-3 rounded-xl border border-gray-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none resize-none disabled:bg-gray-100 disabled:text-gray-500 transition-colors min-h-[48px] max-h-[120px]"
        />
        <button
          type="submit"
          disabled={isDisabled || !content.trim()}
          className="px-6 py-3 bg-blue-500 text-white rounded-xl font-medium hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {isSending ? (
            <>
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" aria-hidden>
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Sending
            </>
          ) : (
            <>
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
              Send
            </>
          )}
        </button>
      </form>
    </div>
  );
}

export default MessageInput;
