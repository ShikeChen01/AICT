/**
 * useAgentStream — consume AgentStreamContext for current agent's buffer and streaming state.
 */

import { useMemo } from 'react';
import { useAgentStreamContext } from '../contexts/AgentStreamContext';
import type { AgentStreamBuffer } from '../types';

export function useAgentStream(agentId: string | null): {
  buffer: AgentStreamBuffer;
  isStreaming: boolean;
  clearBuffer: () => void;
} {
  const { getBuffer, clearBuffer } = useAgentStreamContext();

  const emptyBuffer = useMemo(() => createEmptyBuffer(''), []);
  const buffer = agentId ? getBuffer(agentId) : emptyBuffer;
  const isStreaming = buffer.isStreaming ?? false;

  const clear = () => {
    if (agentId) clearBuffer(agentId);
  };

  return {
    buffer: agentId ? buffer : createEmptyBuffer(''),
    isStreaming,
    clearBuffer: clear,
  };
}

function createEmptyBuffer(agentId: string): AgentStreamBuffer {
  return {
    agentId,
    sessionId: null,
    chunks: [],
    isStreaming: false,
    lastActivity: 0,
  };
}

export default useAgentStream;
