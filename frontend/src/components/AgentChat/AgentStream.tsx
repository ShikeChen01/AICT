/**
 * AgentStream — live streaming output display (text, tool_call, tool_result, message).
 */

import { useMemo } from 'react';
import { MarkdownContent } from '../MarkdownContent';
import type { AgentStreamBuffer, StreamChunk } from '../../types';
import { useAutoFollow } from '../../hooks';
import { Button } from '../ui';

interface AgentStreamProps {
  buffer: AgentStreamBuffer;
  onClear?: () => void;
  /** Compact mode: smaller text, less padding — for use in grid cells */
  compact?: boolean;
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function ChunkRow({ chunk }: { chunk: StreamChunk }) {
  switch (chunk.type) {
    case 'text':
      return (
        <div className="py-1">
          <MarkdownContent>{chunk.content}</MarkdownContent>
          <span className="text-xs text-[var(--text-faint)] ml-1">{formatTime(chunk.timestamp)}</span>
        </div>
      );
    case 'tool_call':
      return (
        <div className="py-1 pl-2 border-l-2 border-[var(--color-warning)]/40 bg-[var(--color-warning-light)] rounded-r text-sm">
          <span className="font-medium text-[var(--color-warning)]">Tool: {chunk.toolName}</span>
          <pre className="mt-1 text-xs text-[var(--text-muted)] overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(chunk.toolInput, null, 2)}
          </pre>
          <span className="text-xs text-[var(--text-faint)]">{formatTime(chunk.timestamp)}</span>
        </div>
      );
    case 'tool_result':
      return (
        <div className={`py-1 pl-2 border-l-2 rounded-r text-sm ${chunk.success ? 'border-[var(--color-success)]/40 bg-[var(--color-success-light)]' : 'border-[var(--color-danger)]/40 bg-[var(--color-danger-light)]'}`}>
          <span className="font-medium">{chunk.toolName}</span> — {chunk.success ? 'OK' : 'Error'}
          <pre className="mt-1 text-xs text-[var(--text-muted)] overflow-x-auto whitespace-pre-wrap max-h-32">
            {chunk.output}
          </pre>
          <span className="text-xs text-[var(--text-faint)]">{formatTime(chunk.timestamp)}</span>
        </div>
      );
    case 'message':
      return (
        <div className="py-1 pl-2 border-l-2 border-[var(--color-primary)]/40 bg-[var(--color-primary)]/5 rounded-r text-sm">
          <MarkdownContent>{chunk.content}</MarkdownContent>
          <span className="text-xs text-[var(--text-faint)]">{formatTime(chunk.timestamp)}</span>
        </div>
      );
    default:
      return null;
  }
}

export function AgentStream({ buffer, onClear, compact }: AgentStreamProps) {
  const streamKey = useMemo(
    () => `${buffer.chunks.length}:${buffer.chunks[buffer.chunks.length - 1]?.timestamp ?? 'none'}`,
    [buffer.chunks]
  );
  const { attachRef, onScroll, isAutoFollow, jumpToLatest } = useAutoFollow<HTMLDivElement>({
    dependencyKey: streamKey,
  });

  if (buffer.chunks.length === 0) {
    return (
      <div className="h-full overflow-y-auto p-4 text-sm text-[var(--text-muted)]">
        Live stream will appear here when the agent responds.
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="ml-2 text-[var(--color-primary)] hover:underline"
          >
            Clear
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="relative h-full min-h-0">
      {!isAutoFollow && (
        <div className="absolute bottom-3 right-3 z-10">
          <Button size="sm" onClick={jumpToLatest}>
            Jump to latest
          </Button>
        </div>
      )}
      <div ref={attachRef} onScroll={onScroll} className={`h-full overflow-y-auto font-mono ${compact ? 'p-2 space-y-1 text-xs' : 'p-4 space-y-2 text-sm'}`}>
      {onClear && (
        <div className="flex justify-end mb-2">
          <button
            type="button"
            onClick={onClear}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
          >
            Clear stream
          </button>
        </div>
      )}
      {buffer.chunks.map((chunk, i) => (
        <ChunkRow key={`${chunk.timestamp}-${i}`} chunk={chunk} />
      ))}
      </div>
    </div>
  );
}

export default AgentStream;
