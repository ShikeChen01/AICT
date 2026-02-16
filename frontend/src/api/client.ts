/**
 * AICT API Client
 * REST + WebSocket client with token auth
 */

import type {
  Task,
  TaskCreate,
  TaskUpdate,
  ChatMessage,
  ChatMessageCreate,
  SendChatMessageResponse,
  Agent,
  AgentStatusWithQueue,
  Ticket,
  TicketCreate,
  Repository,
  UserProfile,
  WSEvent,
  APIError,
} from '../types';

// ─── Configuration ───────────────────────────────────────────────────

const API_BASE = '/api/v1';
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 10000);
/** Longer timeout for chat send; backend may take 30–60s for GM (LangGraph + LLM). */
const CHAT_SEND_TIMEOUT_MS = Number(import.meta.env.VITE_CHAT_SEND_TIMEOUT_MS ?? 120000);

// Token stored in memory; persisted to localStorage so it survives full page reload.
let authToken: string | null = null;

const AUTH_TOKEN_KEY = 'auth_token';

export function setAuthToken(token: string | null): void {
  authToken = token;
  try {
    if (token !== null) {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  } catch {
    // localStorage may be unavailable (private mode, etc.)
  }
}

export function getAuthToken(): string | null {
  return authToken;
}

// ─── HTTP Client ─────────────────────────────────────────────────────

class APIClientError extends Error {
  status: number;
  errorType: string;
  detail?: unknown;

  constructor(
    status: number,
    errorType: string,
    message: string,
    detail?: unknown
  ) {
    super(message);
    this.name = 'APIClientError';
    this.status = status;
    this.errorType = errorType;
    this.detail = detail;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  timeoutMs: number = REQUEST_TIMEOUT_MS
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new APIClientError(
        504,
        'request_timeout',
        `Request timed out after ${timeoutMs}ms`
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let errorData: APIError | null = null;
    try {
      errorData = await response.json();
    } catch {
      // ignore parse error
    }

    throw new APIClientError(
      response.status,
      errorData?.error_type ?? 'unknown_error',
      errorData?.message ?? `HTTP ${response.status}`,
      errorData?.detail
    );
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// ─── REST API Methods ────────────────────────────────────────────────

// Health check
export async function healthCheck(): Promise<{ status: string }> {
  return request<{ status: string }>('GET', '/health');
}

// ─── Chat ────────────────────────────────────────────────────────────

export async function getChatHistory(projectId: string, limit = 100, offset = 0): Promise<ChatMessage[]> {
  return request<ChatMessage[]>('GET', `/chat/history?project_id=${projectId}&limit=${limit}&offset=${offset}`);
}

export async function sendChatMessage(
  projectId: string,
  message: ChatMessageCreate
): Promise<SendChatMessageResponse> {
  return request<SendChatMessageResponse>(
    'POST',
    `/chat/send?project_id=${projectId}`,
    message,
    CHAT_SEND_TIMEOUT_MS
  );
}

export async function getChatMessage(messageId: string): Promise<ChatMessage> {
  return request<ChatMessage>('GET', `/chat/message/${messageId}`);
}

// ─── Tasks ───────────────────────────────────────────────────────────

export async function getTasks(projectId: string, status?: string): Promise<Task[]> {
  let url = `/tasks?project_id=${projectId}`;
  if (status) url += `&status=${status}`;
  return request<Task[]>('GET', url);
}

export async function getTask(taskId: string): Promise<Task> {
  return request<Task>('GET', `/tasks/${taskId}`);
}

export async function createTask(
  projectId: string,
  task: TaskCreate
): Promise<Task> {
  return request<Task>('POST', `/tasks?project_id=${projectId}`, task);
}

export async function updateTask(
  taskId: string,
  update: TaskUpdate
): Promise<Task> {
  return request<Task>('PATCH', `/tasks/${taskId}`, update);
}

export async function updateTaskStatus(taskId: string, status: string): Promise<Task> {
  return request<Task>('PATCH', `/tasks/${taskId}/status?status=${status}`);
}

export async function assignTask(taskId: string, agentId: string): Promise<Task> {
  return request<Task>('POST', `/tasks/${taskId}/assign?agent_id=${agentId}`);
}

export async function deleteTask(taskId: string): Promise<void> {
  return request<void>('DELETE', `/tasks/${taskId}`);
}

// ─── Agents ──────────────────────────────────────────────────────────

export async function getAgents(projectId: string): Promise<Agent[]> {
  return request<Agent[]>('GET', `/agents?project_id=${projectId}`);
}

export async function getAgent(agentId: string): Promise<Agent> {
  return request<Agent>('GET', `/agents/${agentId}`);
}

export async function getAgentStatuses(projectId: string): Promise<AgentStatusWithQueue[]> {
  return request<AgentStatusWithQueue[]>('GET', `/agents/status?project_id=${projectId}`);
}

// ─── Tickets ─────────────────────────────────────────────────────────

export async function getTickets(projectId: string, status?: string): Promise<Ticket[]> {
  let url = `/tickets?project_id=${projectId}`;
  if (status) url += `&status=${status}`;
  return request<Ticket[]>('GET', url);
}

export async function getTicket(ticketId: string): Promise<Ticket> {
  return request<Ticket>('GET', `/tickets/${ticketId}`);
}

export async function createTicket(
  projectId: string,
  fromAgentId: string,
  ticket: TicketCreate
): Promise<Ticket> {
  return request<Ticket>('POST', `/tickets?project_id=${projectId}&from_agent_id=${fromAgentId}`, ticket);
}

export async function replyToTicket(
  ticketId: string,
  fromAgentId: string,
  content: string
): Promise<unknown> {
  return request('POST', `/tickets/${ticketId}/reply?from_agent_id=${fromAgentId}`, { content });
}

export async function closeTicket(ticketId: string, closingAgentId: string): Promise<Ticket> {
  return request<Ticket>('POST', `/tickets/${ticketId}/close?closing_agent_id=${closingAgentId}`);
}

// ─── User Settings ───────────────────────────────────────────────────

export async function getMe(): Promise<UserProfile> {
  return request<UserProfile>('GET', '/auth/me');
}

export async function updateMe(data: {
  display_name?: string | null;
  github_token?: string | null;
}): Promise<UserProfile> {
  return request<UserProfile>('PATCH', '/auth/me', data);
}

// ─── Repositories ────────────────────────────────────────────────────

export async function getRepositories(): Promise<Repository[]> {
  return request<Repository[]>('GET', '/repositories');
}

export async function getRepository(repositoryId: string): Promise<Repository> {
  return request<Repository>('GET', `/repositories/${repositoryId}`);
}

export async function createRepository(data: {
  name: string;
  description?: string | null;
  private?: boolean;
}): Promise<Repository> {
  return request<Repository>('POST', '/repositories', data);
}

export async function importRepository(data: {
  name: string;
  description?: string | null;
  code_repo_url: string;
}): Promise<Repository> {
  return request<Repository>('POST', '/repositories/import', data);
}

export async function updateRepository(
  repositoryId: string,
  data: {
    name?: string | null;
    description?: string | null;
    code_repo_url?: string | null;
  }
): Promise<Repository> {
  return request<Repository>('PATCH', `/repositories/${repositoryId}`, data);
}

export async function deleteRepository(repositoryId: string): Promise<void> {
  return request<void>('DELETE', `/repositories/${repositoryId}`);
}

// Backward-compatible aliases while frontend migrates.
export const getProjects = getRepositories;
export const getProject = getRepository;
export const createProject = createRepository;
export const importProject = importRepository;
export const updateProject = updateRepository;
export const deleteProject = deleteRepository;

// ─── Agent Context ────────────────────────────────────────────────────

export async function getAgentContext(agentId: string): Promise<{
  id: string;
  role: string;
  display_name: string;
  model: string;
  status: string;
  system_prompt: string | null;
  available_tools: { name: string; description: string | null }[];
  recent_messages: Record<string, unknown>[];
  sandbox_id: string | null;
  sandbox_active: boolean;
}> {
  return request('GET', `/agents/${agentId}/context`);
}

// ─── WebSocket Client ────────────────────────────────────────────────

type WSEventHandler = (event: WSEvent) => void;

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private handlers: Set<WSEventHandler> = new Set();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private projectId: string;
  private isConnecting = false;
  private shouldReconnect = true;

  constructor(projectId: string) {
    this.projectId = projectId;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    this.isConnecting = true;
    this.shouldReconnect = true;

    const url = new URL(WS_BASE, window.location.href);
    url.searchParams.set('project_id', this.projectId);
    url.searchParams.set('channels', 'all');
    if (authToken) {
      url.searchParams.set('token', authToken);
    }

    this.ws = new WebSocket(url.toString());

    this.ws.onopen = () => {
      console.log('[WS] Connected');
      this.isConnecting = false;
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const wsEvent = JSON.parse(event.data) as WSEvent;
        this.handlers.forEach((handler) => handler(wsEvent));
      } catch (err) {
        console.error('[WS] Failed to parse message:', err);
      }
    };

    this.ws.onclose = (event) => {
      console.log('[WS] Disconnected:', event.code, event.reason);
      this.isConnecting = false;
      this.ws = null;

      if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        setTimeout(() => this.connect(), delay);
      }
    };

    this.ws.onerror = (error) => {
      console.error('[WS] Error:', error);
    };
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  subscribe(handler: WSEventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  send(message: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('[WS] Cannot send: not connected');
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Factory function for creating WebSocket client
export function createWebSocketClient(projectId: string): WebSocketClient {
  return new WebSocketClient(projectId);
}

// Export error class
export { APIClientError };
