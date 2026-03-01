/**
 * AICT API Client
 * REST + WebSocket client with token auth
 */

import type {
  Task,
  TaskCreate,
  TaskUpdate,
  Attachment,
  ChannelMessage,
  ChannelMessageSend,
  Agent,
  AgentStatusWithQueue,
  AgentSession,
  AgentMessageLog,
  AgentMemoryResponse,
  AgentInterruptRequest,
  AgentInterruptResponse,
  AgentWakeRequest,
  AgentWakeResponse,
  ProjectSettings,
  ProjectSettingsUpdate,
  ProjectUsageResponse,
  Repository,
  UserProfile,
  WSEvent,
  APIError,
  ProjectDocument,
  ProjectDocumentSummary,
  DocumentVersion,
  DocumentVersionSummary,
  DocumentEditRequest,
  AgentTemplate,
  CreateAgentTemplate,
  UpdateAgentTemplate,
  PromptBlockConfig,
  PromptBlockConfigItem,
  UpdateAgentRequest,
} from '../types';

// ─── Configuration ───────────────────────────────────────────────────

const API_BASE = '/api/v1';
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 10000);

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

export interface WorkerHealth {
  started: boolean;
  shutting_down: boolean;
  worker_count: number;
  agent_ids: string[];
}

export async function workerHealthCheck(): Promise<WorkerHealth> {
  return request<WorkerHealth>('GET', '/health/workers');
}

// ─── Messages (NEW — user-to-agent) ────────────────────────────────────

export async function sendMessage(body: ChannelMessageSend): Promise<ChannelMessage> {
  return request<ChannelMessage>(
    'POST',
    '/messages/send',
    body,
    REQUEST_TIMEOUT_MS
  );
}

// ─── Attachments (Phase 6) ───────────────────────────────────────────

/** Upload a single image file and return its metadata (no binary in response). */
export async function uploadAttachment(
  projectId: string,
  file: File
): Promise<Attachment> {
  const formData = new FormData();
  formData.append('project_id', projectId);
  formData.append('file', file);

  const headers: Record<string, string> = {};
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 30_000);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/attachments`, {
      method: 'POST',
      headers,
      body: formData,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Upload failed (${response.status}): ${text}`);
  }
  return response.json() as Promise<Attachment>;
}

/** Fetch raw image bytes for an attachment and return a Blob (use URL.createObjectURL). */
export async function fetchAttachmentBlob(attachmentId: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }
  const response = await fetch(`${API_BASE}/attachments/${attachmentId}/data`, { headers });
  if (!response.ok) {
    throw new Error(`Failed to fetch attachment ${attachmentId}: ${response.status}`);
  }
  return response.blob();
}

export async function getMessages(
  projectId: string,
  agentId: string,
  limit = 100,
  offset = 0
): Promise<ChannelMessage[]> {
  const params = new URLSearchParams({
    project_id: projectId,
    agent_id: agentId,
    limit: String(limit),
    offset: String(offset),
  });
  return request<ChannelMessage[]>(`GET`, `/messages?${params}`);
}

export async function getAllMessages(
  projectId: string,
  limit = 100,
  offset = 0
): Promise<ChannelMessage[]> {
  const params = new URLSearchParams({
    project_id: projectId,
    limit: String(limit),
    offset: String(offset),
  });
  return request<ChannelMessage[]>(`GET`, `/messages/all?${params}`);
}

// ─── Sessions (NEW — agent session history) ───────────────────────────

export async function getSessions(
  projectId: string,
  agentId?: string,
  limit = 50,
  offset = 0
): Promise<AgentSession[]> {
  const params = new URLSearchParams({
    project_id: projectId,
    limit: String(limit),
    offset: String(offset),
  });
  if (agentId) {
    params.set('agent_id', agentId);
  }
  return request<AgentSession[]>(`GET`, `/sessions?${params}`);
}

export async function getSession(sessionId: string): Promise<AgentSession> {
  return request<AgentSession>(`GET`, `/sessions/${sessionId}`);
}

export async function getSessionMessages(
  sessionId: string,
  limit = 100,
  offset = 0
): Promise<AgentMessageLog[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return request<AgentMessageLog[]>(`GET`, `/sessions/${sessionId}/messages?${params}`);
}

// ─── Project Settings (NEW) ───────────────────────────────────────────

export async function getProjectSettings(repositoryId: string): Promise<ProjectSettings> {
  return request<ProjectSettings>(`GET`, `/repositories/${repositoryId}/settings`);
}

export async function updateProjectSettings(
  repositoryId: string,
  data: ProjectSettingsUpdate
): Promise<ProjectSettings> {
  return request<ProjectSettings>(`PATCH`, `/repositories/${repositoryId}/settings`, data);
}

// ─── Project Usage (Phase 4) ─────────────────────────────────────────

export async function getProjectUsage(repositoryId: string): Promise<ProjectUsageResponse> {
  return request<ProjectUsageResponse>('GET', `/repositories/${repositoryId}/usage`);
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

export async function getAgentMemory(agentId: string): Promise<AgentMemoryResponse> {
  return request<AgentMemoryResponse>('GET', `/agents/${agentId}/memory`);
}

export async function interruptAgent(
  agentId: string,
  body: AgentInterruptRequest
): Promise<AgentInterruptResponse> {
  return request<AgentInterruptResponse>('POST', `/agents/${agentId}/interrupt`, body);
}

export interface AgentStopResponse {
  message: string;
}

export async function stopAgent(agentId: string): Promise<AgentStopResponse> {
  return request<AgentStopResponse>('POST', `/agents/${agentId}/stop`);
}

export async function wakeAgent(
  agentId: string,
  body: AgentWakeRequest = {}
): Promise<AgentWakeResponse> {
  return request<AgentWakeResponse>('POST', `/agents/${agentId}/wake`, body);
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
  project_id: string;
  template_id: string | null;
  role: string;
  display_name: string;
  model: string;
  provider: string | null;
  thinking_enabled: boolean;
  status: string;
  system_prompt: string | null;
  available_tools: { name: string; description: string | null }[];
  recent_messages: Record<string, unknown>[];
  sandbox_id: string | null;
  sandbox_active: boolean;
}> {
  return request('GET', `/agents/${agentId}/context`);
}

export async function updateAgent(agentId: string, data: UpdateAgentRequest): Promise<Agent> {
  return request<Agent>('PATCH', `/agents/${agentId}`, data);
}

// ─── Agent Templates ─────────────────────────────────────────────────

export async function listTemplates(projectId: string): Promise<AgentTemplate[]> {
  return request<AgentTemplate[]>('GET', `/templates/projects/${projectId}/templates`);
}

export async function createTemplate(projectId: string, data: CreateAgentTemplate): Promise<AgentTemplate> {
  return request<AgentTemplate>('POST', `/templates/projects/${projectId}/templates`, data);
}

export async function updateTemplate(templateId: string, data: UpdateAgentTemplate): Promise<AgentTemplate> {
  return request<AgentTemplate>('PATCH', `/templates/templates/${templateId}`, data);
}

export async function deleteTemplate(templateId: string): Promise<void> {
  return request<void>('DELETE', `/templates/templates/${templateId}`);
}

// ─── Prompt Blocks ────────────────────────────────────────────────────

export async function listAgentBlocks(agentId: string): Promise<PromptBlockConfig[]> {
  return request<PromptBlockConfig[]>('GET', `/prompt-blocks/agents/${agentId}/blocks`);
}

export async function saveAgentBlocks(agentId: string, blocks: PromptBlockConfigItem[]): Promise<PromptBlockConfig[]> {
  return request<PromptBlockConfig[]>('PUT', `/prompt-blocks/agents/${agentId}/blocks`, { blocks });
}

export async function resetAgentBlock(agentId: string, blockId: string): Promise<PromptBlockConfig> {
  return request<PromptBlockConfig>('POST', `/prompt-blocks/agents/${agentId}/blocks/${blockId}/reset`);
}

export async function listTemplateBlocks(templateId: string): Promise<PromptBlockConfig[]> {
  return request<PromptBlockConfig[]>('GET', `/prompt-blocks/templates/${templateId}/blocks`);
}

export async function saveTemplateBlocks(templateId: string, blocks: PromptBlockConfigItem[]): Promise<PromptBlockConfig[]> {
  return request<PromptBlockConfig[]>('PUT', `/prompt-blocks/templates/${templateId}/blocks`, { blocks });
}

export async function getDefaultBlocks(baseRole: string): Promise<PromptBlockConfigItem[]> {
  return request<PromptBlockConfigItem[]>('GET', `/prompt-blocks/defaults/${baseRole}`);
}

// ─── Document Versioning ─────────────────────────────────────────────

export async function editDocument(
  repositoryId: string,
  docType: string,
  data: DocumentEditRequest,
): Promise<ProjectDocument> {
  return request<ProjectDocument>('PUT', `/repositories/${repositoryId}/documents/${docType}`, data);
}

export async function listDocumentVersions(
  repositoryId: string,
  docType: string,
): Promise<DocumentVersionSummary[]> {
  return request<DocumentVersionSummary[]>('GET', `/repositories/${repositoryId}/documents/${docType}/versions`);
}

export async function getDocumentVersion(
  repositoryId: string,
  docType: string,
  versionNumber: number,
): Promise<DocumentVersion> {
  return request<DocumentVersion>('GET', `/repositories/${repositoryId}/documents/${docType}/versions/${versionNumber}`);
}

export async function revertDocument(
  repositoryId: string,
  docType: string,
  versionNumber: number,
): Promise<ProjectDocument> {
  return request<ProjectDocument>('POST', `/repositories/${repositoryId}/documents/${docType}/revert`, { version_number: versionNumber });
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
  private wsChannels: string;
  private isConnecting = false;
  private shouldReconnect = true;

  constructor(projectId: string, wsChannels: string = 'all') {
    this.projectId = projectId;
    this.wsChannels = wsChannels;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    if (!authToken) {
      return;
    }

    this.isConnecting = true;
    this.shouldReconnect = true;

    const url = new URL(WS_BASE, window.location.href);
    url.searchParams.set('project_id', this.projectId);
    url.searchParams.set('channels', this.wsChannels);
    url.searchParams.set('token', authToken);

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
      console.warn('[WS] Closed:', event.code, event.reason);
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
export function createWebSocketClient(projectId: string, channels: string = 'all'): WebSocketClient {
  return new WebSocketClient(projectId, channels);
}

// Export error class
export { APIClientError };

// ─── Test Login (dev only) ────────────────────────────────────────────

/** POST /testfads89213xlogin — returns the shared api_token on success. */
export async function testLogin(email: string, password: string): Promise<{ token: string }> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 10_000);
  let response: Response;
  try {
    response = await fetch('/testfads89213xlogin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(data.detail ?? `HTTP ${response.status}`);
  }
  return response.json() as Promise<{ token: string }>;
}

// ─── Architecture Documents (Phase 10) ───────────────────────────────

export async function listDocuments(repositoryId: string): Promise<ProjectDocumentSummary[]> {
  return request<ProjectDocumentSummary[]>('GET', `/repositories/${repositoryId}/documents`);
}

export async function getDocument(repositoryId: string, docType: string): Promise<ProjectDocument> {
  return request<ProjectDocument>(
    'GET',
    `/repositories/${repositoryId}/documents/${encodeURIComponent(docType)}`
  );
}
