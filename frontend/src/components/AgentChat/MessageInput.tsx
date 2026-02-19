/**
 * MessageInput — user message composer for agent chat.
 */

import { useState, useCallback, type FormEvent, type KeyboardEvent } from 'react';
import { Button, Textarea } from '../ui';

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
    <div className="border-t border-[var(--border-color)] bg-[var(--surface-muted)] p-4">
      {isStreaming && (
        <div className="mb-2 flex items-center gap-2 text-sm text-amber-700">
          <div className="w-2 h-2 bg-amber-500 rounded-full animate-pulse" />
          Agent is responding...
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
          disabled={isDisabled}
          rows={1}
          className="min-h-[48px] max-h-[120px] flex-1 resize-none"
        />
        <Button
          type="submit"
          disabled={isDisabled || !content.trim()}
          className="h-12 rounded-xl px-6"
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
        </Button>
      </form>
    </div>
  );
}

export default MessageInput;
