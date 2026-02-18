/**
 * AgentStream — live streaming output display (text, tool_call, tool_result, message).
 */

import { useRef, useEffect } from 'react';
import { MarkdownContent } from '../MarkdownContent';
import type { AgentStreamBuffer, StreamChunk } from '../../types';

interface AgentStreamProps {
  buffer: AgentStreamBuffer;
  onClear?: () => void;
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
          <span className="text-xs text-gray-400 ml-1">{formatTime(chunk.timestamp)}</span>
        </div>
      );
    case 'tool_call':
      return (
        <div className="py-1 pl-2 border-l-2 border-amber-400 bg-amber-50 rounded-r text-sm">
          <span className="font-medium text-amber-800">Tool: {chunk.toolName}</span>
          <pre className="mt-1 text-xs text-gray-600 overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(chunk.toolInput, null, 2)}
          </pre>
          <span className="text-xs text-gray-400">{formatTime(chunk.timestamp)}</span>
        </div>
      );
    case 'tool_result':
      return (
        <div className={`py-1 pl-2 border-l-2 rounded-r text-sm ${chunk.success ? 'border-green-400 bg-green-50' : 'border-red-400 bg-red-50'}`}>
          <span className="font-medium">{chunk.toolName}</span> — {chunk.success ? 'OK' : 'Error'}
          <pre className="mt-1 text-xs text-gray-600 overflow-x-auto whitespace-pre-wrap max-h-32">
            {chunk.output}
          </pre>
          <span className="text-xs text-gray-400">{formatTime(chunk.timestamp)}</span>
        </div>
      );
    case 'message':
      return (
        <div className="py-1 pl-2 border-l-2 border-blue-400 bg-blue-50 rounded-r text-sm">
          <MarkdownContent>{chunk.content}</MarkdownContent>
          <span className="text-xs text-gray-400">{formatTime(chunk.timestamp)}</span>
        </div>
      );
    default:
      return null;
  }
}

export function AgentStream({ buffer, onClear }: AgentStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [buffer.chunks.length]);

  if (buffer.chunks.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto p-4 text-sm text-gray-500">
        Live stream will appear here when the agent responds.
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="ml-2 text-blue-600 hover:underline"
          >
            Clear
          </button>
        )}
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-sm">
      {onClear && (
        <div className="flex justify-end mb-2">
          <button
            type="button"
            onClick={onClear}
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            Clear stream
          </button>
        </div>
      )}
      {buffer.chunks.map((chunk, i) => (
        <ChunkRow key={`${chunk.timestamp}-${i}`} chunk={chunk} />
      ))}
    </div>
  );
}

export default AgentStream;
