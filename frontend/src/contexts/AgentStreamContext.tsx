/**
 * AgentStreamContext — WebSocket connection and per-agent stream buffers.
 * Subscribes to agent_text, agent_tool_call, agent_tool_result, agent_message.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createWebSocketClient, getAuthToken, WebSocketClient } from '../api/client';
import type {
  AgentStreamBuffer,
  AgentTextData,
  AgentToolCallData,
  AgentToolResultData,
  AgentMessageData,
  StreamChunk,
} from '../types';

const MAX_CHUNKS = 500;

function createEmptyBuffer(agentId: string): AgentStreamBuffer {
  return {
    agentId,
    sessionId: null,
    chunks: [],
    isStreaming: false,
    lastActivity: 0,
  };
}

interface AgentStreamContextValue {
  buffers: Map<string, AgentStreamBuffer>;
  inspectedAgentId: string | null;
  setInspectedAgent: (agentId: string | null) => void;
  getBuffer: (agentId: string) => AgentStreamBuffer;
  clearBuffer: (agentId: string) => void;
  isConnected: boolean;
}

const AgentStreamContext = createContext<AgentStreamContextValue | null>(null);

export function AgentStreamProvider({
  projectId,
  children,
}: {
  projectId: string | null;
  children: React.ReactNode;
}) {
  const clientRef = useRef<WebSocketClient | null>(null);
  const [buffers, setBuffers] = useState<Map<string, AgentStreamBuffer>>(new Map());
  const [inspectedAgentId, setInspectedAgentId] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const appendChunk = useCallback((agentId: string, chunk: StreamChunk) => {
    const now = Date.now();
    setBuffers((prev) => {
      const next = new Map(prev);
      const buf = next.get(agentId) ?? createEmptyBuffer(agentId);
      const chunks = [...buf.chunks, chunk].slice(-MAX_CHUNKS);
      next.set(agentId, {
        ...buf,
        chunks,
        lastActivity: now,
        isStreaming: chunk.type === 'text' || chunk.type === 'tool_call',
      });
      return next;
    });
  }, []);

  const setStreaming = useCallback((agentId: string, streaming: boolean) => {
    setBuffers((prev) => {
      const next = new Map(prev);
      const buf = next.get(agentId);
      if (buf) {
        next.set(agentId, { ...buf, isStreaming: streaming });
      }
      return next;
    });
  }, []);

  const token = getAuthToken();

  useEffect(() => {
    if (!projectId || !token) {
      clientRef.current?.disconnect();
      clientRef.current = null;
      setBuffers(new Map());
      setIsConnected(false);
      return;
    }

    const client = createWebSocketClient(projectId);
    clientRef.current = client;

    const checkConnected = () => setIsConnected(client.isConnected);

    const unsub = client.subscribe((event) => {
      checkConnected();
      const data = event.data as Record<string, unknown>;
      const agentId = typeof data?.agent_id === 'string' ? data.agent_id : null;
      if (!agentId) return;

      const ts = new Date().toISOString();

      switch (event.type) {
        case 'agent_text': {
          const d = data as unknown as AgentTextData;
          const content = d?.content ?? '';
          appendChunk(agentId, { type: 'text', content, timestamp: ts });
          break;
        }
        case 'agent_tool_call': {
          const d = data as unknown as AgentToolCallData;
          appendChunk(agentId, {
            type: 'tool_call',
            toolName: d?.tool_name ?? '',
            toolInput: (d?.tool_input as Record<string, unknown>) ?? {},
            timestamp: ts,
          });
          break;
        }
        case 'agent_tool_result': {
          const d = data as unknown as AgentToolResultData;
          appendChunk(agentId, {
            type: 'tool_result',
            toolName: d?.tool_name ?? '',
            output: d?.output ?? '',
            success: d?.success ?? false,
            timestamp: ts,
          });
          setStreaming(agentId, false);
          break;
        }
        case 'agent_message': {
          const d = data as unknown as AgentMessageData;
          appendChunk(agentId, {
            type: 'message',
            content: d?.content ?? '',
            from: String(d?.from_agent_id ?? agentId),
            timestamp: ts,
          });
          setStreaming(agentId, false);
          break;
        }
        default:
          break;
      }
    });

    client.connect();
    const interval = setInterval(checkConnected, 500);

    return () => {
      clearInterval(interval);
      unsub();
      client.disconnect();
      clientRef.current = null;
      setIsConnected(false);
    };
  }, [projectId, token, appendChunk, setStreaming]);

  const getBuffer = useCallback(
    (agentId: string): AgentStreamBuffer => {
      return buffers.get(agentId) ?? createEmptyBuffer(agentId);
    },
    [buffers]
  );

  const clearBuffer = useCallback((agentId: string) => {
    setBuffers((prev) => {
      const next = new Map(prev);
      next.set(agentId, createEmptyBuffer(agentId));
      return next;
    });
  }, []);

  const value: AgentStreamContextValue = useMemo(
    () => ({
      buffers,
      inspectedAgentId,
      setInspectedAgent: setInspectedAgentId,
      getBuffer,
      clearBuffer,
      isConnected,
    }),
    [buffers, inspectedAgentId, getBuffer, clearBuffer, isConnected]
  );

  return (
    <AgentStreamContext.Provider value={value}>
      {children}
    </AgentStreamContext.Provider>
  );
}

export function useAgentStreamContext(): AgentStreamContextValue {
  const ctx = useContext(AgentStreamContext);
  if (!ctx) {
    throw new Error('useAgentStreamContext must be used within AgentStreamProvider');
  }
  return ctx;
}
