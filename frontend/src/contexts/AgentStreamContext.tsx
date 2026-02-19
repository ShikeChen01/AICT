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
  SystemMessageData,
  StreamChunk,
  ActivityLogItem,
  AgentRole,
} from '../types';

const MAX_CHUNKS = 500;
const MAX_ACTIVITY = 400;

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
  activityLogs: ActivityLogItem[];
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
  const [activityLogs, setActivityLogs] = useState<ActivityLogItem[]>([]);
  const [inspectedAgentId, setInspectedAgentId] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const appendChunk = useCallback((agentId: string, chunk: StreamChunk) => {
    const now = Date.now();
    setBuffers((prev) => {
      const next = new Map(prev);
      const buf = next.get(agentId) ?? createEmptyBuffer(agentId);
      let chunks = buf.chunks;
      if (chunk.type === 'text') {
        const last = buf.chunks[buf.chunks.length - 1];
        if (last?.type === 'text') {
          chunks = [
            ...buf.chunks.slice(0, -1),
            {
              ...last,
              content: `${last.content}${chunk.content}`,
              timestamp: chunk.timestamp,
            },
          ];
        } else {
          chunks = [...buf.chunks, chunk];
        }
      } else {
        chunks = [...buf.chunks, chunk];
      }
      chunks = chunks.slice(-MAX_CHUNKS);
      next.set(agentId, {
        ...buf,
        chunks,
        lastActivity: now,
        isStreaming: chunk.type === 'text' || chunk.type === 'tool_call',
      });
      return next;
    });
  }, []);

  const appendActivity = useCallback((item: ActivityLogItem) => {
    setActivityLogs((prev) => [...prev, item].slice(-MAX_ACTIVITY));
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
      setActivityLogs([]);
      setIsConnected(false);
      return;
    }

    const client = createWebSocketClient(projectId);
    clientRef.current = client;

    const checkConnected = () => setIsConnected(client.isConnected);

    const unsub = client.subscribe((event) => {
      checkConnected();
      const data = event.data as Record<string, unknown>;
      const ts = new Date().toISOString();
      const agentId = typeof data?.agent_id === 'string' ? data.agent_id : null;
      const role = (data?.agent_role as AgentRole) ?? 'engineer';

      switch (event.type) {
        case 'agent_text': {
          if (!agentId) break;
          const d = data as unknown as AgentTextData;
          const content = d?.content ?? '';
          appendChunk(agentId, { type: 'text', content, timestamp: ts });
          appendActivity({
            id: `${agentId}-${Date.now()}-text`,
            timestamp: ts,
            project_id: projectId,
            agent_id: agentId,
            agent_role: d?.agent_role ?? role,
            log_type: 'thought',
            content,
          });
          break;
        }
        case 'agent_tool_call': {
          if (!agentId) break;
          const d = data as unknown as AgentToolCallData;
          appendChunk(agentId, {
            type: 'tool_call',
            toolName: d?.tool_name ?? '',
            toolInput: (d?.tool_input as Record<string, unknown>) ?? {},
            timestamp: ts,
          });
          appendActivity({
            id: `${agentId}-${Date.now()}-tool-call`,
            timestamp: ts,
            project_id: projectId,
            agent_id: agentId,
            agent_role: d?.agent_role ?? role,
            log_type: 'tool_call',
            content: `Calling ${d?.tool_name ?? 'tool'}`,
            tool_name: d?.tool_name ?? '',
            tool_input: (d?.tool_input as Record<string, unknown>) ?? {},
          });
          break;
        }
        case 'agent_tool_result': {
          if (!agentId) break;
          const d = data as unknown as AgentToolResultData;
          appendChunk(agentId, {
            type: 'tool_result',
            toolName: d?.tool_name ?? '',
            output: d?.output ?? '',
            success: d?.success ?? false,
            timestamp: ts,
          });
          appendActivity({
            id: `${agentId}-${Date.now()}-tool-result`,
            timestamp: ts,
            project_id: projectId,
            agent_id: agentId,
            agent_role: role,
            log_type: d?.success ? 'tool_result' : 'error',
            content: d?.output ?? '',
            tool_name: d?.tool_name ?? '',
            tool_output: d?.output ?? '',
          });
          setStreaming(agentId, false);
          break;
        }
        case 'agent_message': {
          const d = data as unknown as AgentMessageData;
          const messageAgentId = String(d?.from_agent_id ?? '');
          if (!messageAgentId) break;
          appendChunk(messageAgentId, {
            type: 'message',
            content: d?.content ?? '',
            from: messageAgentId,
            timestamp: ts,
          });
          appendActivity({
            id: `${messageAgentId}-${Date.now()}-message`,
            timestamp: ts,
            project_id: projectId,
            agent_id: messageAgentId,
            agent_role: role,
            log_type: 'message',
            content: d?.content ?? '',
          });
          setStreaming(messageAgentId, false);
          break;
        }
        case 'agent_log': {
          const log = data as unknown as ActivityLogItem;
          appendActivity({
            ...log,
            id: `${log.agent_id}-${Date.now()}-agent-log`,
            timestamp: ts,
            project_id: log.project_id ?? projectId,
          });
          break;
        }
        case 'system_message': {
          const d = data as unknown as SystemMessageData;
          if (!inspectedAgentId) break;
          appendChunk(inspectedAgentId, {
            type: 'message',
            content: d?.content ?? '',
            from: 'system',
            timestamp: ts,
          });
          appendActivity({
            id: `system-${Date.now()}`,
            timestamp: ts,
            project_id: projectId,
            agent_id: inspectedAgentId,
            agent_role: 'manager',
            log_type: 'message',
            content: d?.content ?? '',
          });
          setStreaming(inspectedAgentId, false);
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
  }, [projectId, token, appendChunk, setStreaming, inspectedAgentId, appendActivity]);

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
      activityLogs,
      inspectedAgentId,
      setInspectedAgent: setInspectedAgentId,
      getBuffer,
      clearBuffer,
      isConnected,
    }),
    [buffers, activityLogs, inspectedAgentId, getBuffer, clearBuffer, isConnected]
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

export function useOptionalAgentStreamContext(): AgentStreamContextValue | null {
  return useContext(AgentStreamContext);
}
