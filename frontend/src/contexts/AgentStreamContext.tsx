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
import { createWebSocketClient, getAuthToken, WebSocketClient, workerHealthCheck } from '../api/client';
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
  BackendLogItem,
  BackendLogSnapshotData,
  UsageUpdateData,
} from '../types';

const MAX_CHUNKS = 500;
const MAX_ACTIVITY = 400;
const MAX_BACKEND_LOGS = 1000;
const MAX_USAGE_EVENTS = 500;

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
  backendLogs: BackendLogItem[];
  usageEvents: UsageUpdateData[];
  inspectedAgentId: string | null;
  setInspectedAgent: (agentId: string | null) => void;
  getBuffer: (agentId: string) => AgentStreamBuffer;
  clearBuffer: (agentId: string) => void;
  clearBackendLogs: () => void;
  clearUsageEvents: () => void;
  isConnected: boolean;
  workersReady: boolean;
}

const AgentStreamContext = createContext<AgentStreamContextValue | null>(null);

export function AgentStreamProvider({
  projectId,
  wsChannels = 'agent_stream,messages,kanban,agents,activity,workflow,usage',
  backendLogsWsChannels = 'backend_logs',
  enablePrimaryStream = true,
  enableBackendLogStream = true,
  children,
}: {
  projectId: string | null;
  wsChannels?: string;
  backendLogsWsChannels?: string;
  enablePrimaryStream?: boolean;
  enableBackendLogStream?: boolean;
  children: React.ReactNode;
}) {
  const primaryClientRef = useRef<WebSocketClient | null>(null);
  const backendLogClientRef = useRef<WebSocketClient | null>(null);
  const [buffers, setBuffers] = useState<Map<string, AgentStreamBuffer>>(new Map());
  const [activityLogs, setActivityLogs] = useState<ActivityLogItem[]>([]);
  const [backendLogs, setBackendLogs] = useState<BackendLogItem[]>([]);
  const [usageEvents, setUsageEvents] = useState<UsageUpdateData[]>([]);
  const [inspectedAgentId, setInspectedAgentId] = useState<string | null>(null);
  const [primaryConnected, setPrimaryConnected] = useState(false);
  const [backendLogConnected, setBackendLogConnected] = useState(false);
  const [workersReady, setWorkersReady] = useState(false);

  // Ref mirrors inspectedAgentId so the WS handler can read the latest value
  // without forcing a reconnection every time the user selects a different agent.
  const inspectedAgentRef = useRef(inspectedAgentId);
  inspectedAgentRef.current = inspectedAgentId;

  // Track the highest backend-log seq we've seen so we can skip duplicates
  // that arrive between a snapshot delivery and incremental events.
  const backendLogSeqRef = useRef(0);

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
    if (!enablePrimaryStream || !projectId || !token) {
      primaryClientRef.current?.disconnect();
      primaryClientRef.current = null;
      setBuffers(new Map());
      setActivityLogs([]);
      setPrimaryConnected(false);
      return;
    }

    const client = createWebSocketClient(projectId, wsChannels);
    primaryClientRef.current = client;

    const checkConnected = () => setPrimaryConnected(client.isConnected);

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
        case 'usage_update': {
          const d = data as unknown as UsageUpdateData;
          setUsageEvents((prev) => [d, ...prev].slice(0, MAX_USAGE_EVENTS));
          break;
        }
        case 'system_message': {
          const d = data as unknown as SystemMessageData;
          const currentInspected = inspectedAgentRef.current;
          if (!currentInspected) break;
          appendChunk(currentInspected, {
            type: 'message',
            content: d?.content ?? '',
            from: 'system',
            timestamp: ts,
          });
          appendActivity({
            id: `system-${Date.now()}`,
            timestamp: ts,
            project_id: projectId,
            agent_id: currentInspected,
            agent_role: 'manager',
            log_type: 'message',
            content: d?.content ?? '',
          });
          setStreaming(currentInspected, false);
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
      primaryClientRef.current = null;
      setPrimaryConnected(false);
    };
  }, [projectId, token, wsChannels, enablePrimaryStream, appendChunk, setStreaming, appendActivity]);

  useEffect(() => {
    if (!enableBackendLogStream || !projectId || !token) {
      backendLogClientRef.current?.disconnect();
      backendLogClientRef.current = null;
      setBackendLogs([]);
      setBackendLogConnected(false);
      return;
    }

    const client = createWebSocketClient(projectId, backendLogsWsChannels);
    backendLogClientRef.current = client;

    const checkConnected = () => setBackendLogConnected(client.isConnected);

    const unsub = client.subscribe((event) => {
      checkConnected();
      const data = event.data as Record<string, unknown>;

      switch (event.type) {
        case 'backend_log': {
          const d = data as unknown as BackendLogItem;
          if (typeof d?.seq === 'number' && d.seq <= backendLogSeqRef.current) break;
          if (typeof d?.seq === 'number') backendLogSeqRef.current = d.seq;
          setBackendLogs((prev) => [...prev, d].slice(-MAX_BACKEND_LOGS));
          break;
        }
        case 'backend_log_snapshot': {
          const d = data as unknown as BackendLogSnapshotData;
          const items = (d?.items ?? []).slice(-MAX_BACKEND_LOGS);
          if (typeof d?.latest_seq === 'number') backendLogSeqRef.current = d.latest_seq;
          setBackendLogs(items);
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
      backendLogClientRef.current = null;
      setBackendLogConnected(false);
    };
  }, [projectId, token, backendLogsWsChannels, enableBackendLogStream]);

  // Poll worker health every 10s so the user knows if the backend workers are down
  useEffect(() => {
    if (!projectId || !token) {
      setWorkersReady(false);
      return;
    }

    let cancelled = false;

    const check = async () => {
      try {
        const health = await workerHealthCheck();
        if (!cancelled) setWorkersReady(health.started && health.worker_count > 0);
      } catch {
        if (!cancelled) setWorkersReady(false);
      }
    };

    check();
    const timer = setInterval(check, 10_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [projectId, token]);

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

  const clearBackendLogs = useCallback(() => {
    setBackendLogs([]);
  }, []);

  const clearUsageEvents = useCallback(() => {
    setUsageEvents([]);
  }, []);

  const isConnected = useMemo(() => {
    if (enablePrimaryStream && enableBackendLogStream) {
      return primaryConnected && backendLogConnected;
    }
    if (enablePrimaryStream) {
      return primaryConnected;
    }
    if (enableBackendLogStream) {
      return backendLogConnected;
    }
    return false;
  }, [enablePrimaryStream, enableBackendLogStream, primaryConnected, backendLogConnected]);

  const value: AgentStreamContextValue = useMemo(
    () => ({
      buffers,
      activityLogs,
      backendLogs,
      usageEvents,
      inspectedAgentId,
      setInspectedAgent: setInspectedAgentId,
      getBuffer,
      clearBuffer,
      clearBackendLogs,
      clearUsageEvents,
      isConnected,
      workersReady,
    }),
    [
      buffers,
      activityLogs,
      backendLogs,
      usageEvents,
      inspectedAgentId,
      getBuffer,
      clearBuffer,
      clearBackendLogs,
      clearUsageEvents,
      isConnected,
      workersReady,
    ]
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
