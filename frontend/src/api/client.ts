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
  ProjectSecret,
  ProjectSecretUpsert,
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
  PromptMeta,
  ToolConfig,
  ToolConfigUpdateItem,
  ToolConfigMeta,
  SandboxConfig,
  SandboxConfigCreate,
  SandboxConfigUpdate,
  Sandbox,
  SandboxConnectionInfo,
  SandboxSnapshot,
  CreateSandboxRequest,
  AssignSandboxRequest,
  SandboxUpdateRequest,
  SandboxSnapshotRequest,
  SandboxRestoreRequest,
} from '../types';

// ─── Configuration ───────────────────────────────────────────────────

/** When set at build time, API and WebSocket use this backend (e.g. Cloud Run URL). */
const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL as string | undefined)?.replace(/\/$/, '');
const API_BASE = BACKEND_URL ? `${BACKEND_URL}/api/v1` : '/api/v1';
/** WebSocket base URL for /ws/* — same host as API when BACKEND_URL is set. */
function getWsBase(): string {
  if (BACKEND_URL) {
    const wsProtocol = BACKEND_URL.startsWith('https') ? 'wss:' : 'ws:';
    const host = BACKEND_URL.replace(/^https?:\/\//, '');
    return `${wsProtocol}//${host}/ws`;
  }
  return `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
}
const WS_BASE = getWsBase();
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 10000);

/** Build full WebSocket URL for screen stream or VNC (caller appends query string or path). */
export function getSandboxWsBase(): string {
  return getWsBase();
}

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

    const detail = errorData?.detail;
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? (detail as { msg?: string }[]).map((e) => e.msg).filter(Boolean).join('; ') || undefined
          : undefined;
    const message = msg ?? errorData?.message ?? `HTTP ${response.status}`;

    throw new APIClientError(
      response.status,
      errorData?.error_type ?? 'unknown_error',
      message,
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

// ─── Project secrets ────────────────────────────────────────────────

export async function listProjectSecrets(repositoryId: string): Promise<ProjectSecret[]> {
  return request<ProjectSecret[]>(`GET`, `/repositories/${repositoryId}/secrets`);
}

export async function upsertProjectSecret(
  repositoryId: string,
  data: ProjectSecretUpsert
): Promise<ProjectSecret> {
  return request<ProjectSecret>(`POST`, `/repositories/${repositoryId}/secrets`, data);
}

export async function deleteProjectSecret(repositoryId: string, name: string): Promise<void> {
  return request<void>(`DELETE`, `/repositories/${repositoryId}/secrets/${encodeURIComponent(name)}`);
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
  code_repo_url?: string | null;
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

/** Spawn a new agent from a template (agent design). */
export async function spawnFromTemplate(
  templateId: string,
  data?: { display_name?: string; sandbox_persist?: boolean },
): Promise<Agent> {
  return request<Agent>('POST', `/templates/templates/${templateId}/spawn`, data ?? {});
}

/** Delete a non-core agent. Manager and CTO are protected. */
export async function deleteAgent(agentId: string): Promise<{ ok: boolean; message: string }> {
  return request<{ ok: boolean; message: string }>('DELETE', `/agents/${agentId}`);
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

export async function getPromptMeta(params?: { model?: string; agent_id?: string }): Promise<PromptMeta> {
  const qs = new URLSearchParams();
  if (params?.model) qs.set('model', params.model);
  if (params?.agent_id) qs.set('agent_id', params.agent_id);
  const query = qs.toString() ? `?${qs.toString()}` : '';
  return request<PromptMeta>('GET', `/prompt-blocks/meta${query}`);
}

// ─── Tool Configs ─────────────────────────────────────────────────────

export async function listAgentTools(agentId: string): Promise<ToolConfig[]> {
  return request<ToolConfig[]>('GET', `/tool-configs/agents/${agentId}/tools`);
}

export async function saveAgentTools(
  agentId: string,
  tools: ToolConfigUpdateItem[],
): Promise<ToolConfig[]> {
  return request<ToolConfig[]>('PUT', `/tool-configs/agents/${agentId}/tools`, { tools });
}

export async function resetAgentTool(
  agentId: string,
  toolConfigId: string,
): Promise<ToolConfig> {
  return request<ToolConfig>('POST', `/tool-configs/agents/${agentId}/tools/${toolConfigId}/reset`);
}

export async function getToolConfigMeta(agentId: string): Promise<ToolConfigMeta> {
  return request<ToolConfigMeta>('GET', `/tool-configs/meta?agent_id=${agentId}`);
}

// ─── MCP Servers ──────────────────────────────────────────────────────

export async function listMcpServers(agentId: string): Promise<import('../types').McpServer[]> {
  return request<import('../types').McpServer[]>('GET', `/mcp-servers/agents/${agentId}`);
}

export async function createMcpServer(
  agentId: string,
  data: import('../types').McpServerCreate,
): Promise<import('../types').McpServer> {
  return request<import('../types').McpServer>('POST', `/mcp-servers/agents/${agentId}`, data);
}

export async function updateMcpServer(
  serverId: string,
  data: import('../types').McpServerUpdate,
): Promise<import('../types').McpServer> {
  return request<import('../types').McpServer>('PUT', `/mcp-servers/${serverId}`, data);
}

export async function deleteMcpServer(serverId: string): Promise<void> {
  return request<void>('DELETE', `/mcp-servers/${serverId}`);
}

export async function syncMcpServer(serverId: string): Promise<import('../types').McpSyncResult> {
  return request<import('../types').McpSyncResult>('POST', `/mcp-servers/${serverId}/sync`);
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

// ─── Sandboxes (v3) ─────────────────────────────────────────────────────

export async function listSandboxes(projectId: string): Promise<Sandbox[]> {
  return request<Sandbox[]>('GET', `/sandboxes?project_id=${projectId}`);
}

export async function createSandbox(
  projectId: string,
  configId?: string | null,
  name?: string | null,
  requiresDesktop?: boolean,
): Promise<Sandbox> {
  return request<Sandbox>(
    'POST',
    '/sandboxes',
    { project_id: projectId, config_id: configId ?? null, name: name ?? null, ...(requiresDesktop !== undefined ? { requires_desktop: requiresDesktop } : {}) } as CreateSandboxRequest,
    120_000,
  );
}

/** Create a desktop (sandbox with requires_desktop=true). */
export async function createDesktop(
  projectId: string,
  configId?: string | null,
  name?: string | null,
): Promise<Sandbox> {
  return createSandbox(projectId, configId, name, true);
}

export async function assignSandbox(sandboxId: string, agentId: string): Promise<Sandbox> {
  return request<Sandbox>(
    'POST',
    `/sandboxes/${sandboxId}/assign`,
    { agent_id: agentId } as AssignSandboxRequest,
  );
}

/** Convenience: create a sandbox and immediately assign it to an agent. */
export async function createAndAssignSandbox(
  projectId: string,
  agentId: string,
  configId?: string | null,
): Promise<Sandbox> {
  const sandbox = await createSandbox(projectId, configId);
  return assignSandbox(sandbox.id, agentId);
}

export async function unassignSandbox(sandboxId: string): Promise<Sandbox> {
  return request<Sandbox>('POST', `/sandboxes/${sandboxId}/unassign`);
}

export async function updateSandbox(sandboxId: string, data: SandboxUpdateRequest): Promise<Sandbox> {
  return request<Sandbox>('PATCH', `/sandboxes/${sandboxId}`, data);
}

export async function getSandboxConnectionInfo(sandboxId: string): Promise<SandboxConnectionInfo> {
  return request<SandboxConnectionInfo>('GET', `/sandboxes/${sandboxId}/connect`);
}

export async function restartSandbox(sandboxId: string): Promise<{ ok: boolean; sandbox_id: string; action: string; message: string }> {
  return request<{ ok: boolean; sandbox_id: string; action: string; message: string }>('POST', `/sandboxes/${sandboxId}/restart`, undefined, 120_000);
}

export async function checkSandboxHealth(sandboxId: string): Promise<{ ok: boolean; sandbox_id: string; status: string }> {
  return request<{ ok: boolean; sandbox_id: string; status: string }>('GET', `/sandboxes/${sandboxId}/health`);
}

export async function destroySandbox(sandboxId: string): Promise<void> {
  return request<void>('DELETE', `/sandboxes/${sandboxId}`);
}

export async function applySandboxConfig(sandboxId: string): Promise<Sandbox> {
  return request<Sandbox>('POST', `/sandboxes/${sandboxId}/apply-config`, undefined, 300_000);
}

export async function createSandboxSnapshot(
  sandboxId: string,
  label: string,
): Promise<SandboxSnapshot> {
  return request<SandboxSnapshot>(
    'POST',
    `/sandboxes/${sandboxId}/snapshot`,
    { label } as SandboxSnapshotRequest,
  );
}

export async function restoreSandboxSnapshot(
  sandboxId: string,
  snapshotId: string,
): Promise<Sandbox> {
  return request<Sandbox>(
    'POST',
    `/sandboxes/${sandboxId}/restore`,
    { snapshot_id: snapshotId } as SandboxRestoreRequest,
    300_000,
  );
}

export async function listSandboxSnapshots(sandboxId: string): Promise<SandboxSnapshot[]> {
  return request<SandboxSnapshot[]>('GET', `/sandboxes/${sandboxId}/snapshots`);
}

// ─── Sandbox OS Images ───────────────────────────────────────────────

export interface SandboxOSImage {
  slug: string;
  display_name: string;
  os_family: 'linux' | 'windows';
  default: boolean;
  resources: {
    requests: { cpu: string; memory: string };
    limits?: { cpu: string; memory: string };
  };
}

export async function listSandboxImages(): Promise<SandboxOSImage[]> {
  return request<SandboxOSImage[]>('GET', '/sandboxes/images');
}

// ─── Sandbox Configs (user-level) ────────────────────────────────────

export async function listSandboxConfigs(): Promise<SandboxConfig[]> {
  return request<SandboxConfig[]>('GET', '/sandbox-configs');
}

export async function createSandboxConfig(data: SandboxConfigCreate): Promise<SandboxConfig> {
  return request<SandboxConfig>('POST', '/sandbox-configs', data);
}

export async function getSandboxConfig(configId: string): Promise<SandboxConfig> {
  return request<SandboxConfig>('GET', `/sandbox-configs/${configId}`);
}

export async function updateSandboxConfig(configId: string, data: SandboxConfigUpdate): Promise<SandboxConfig> {
  return request<SandboxConfig>('PATCH', `/sandbox-configs/${configId}`, data);
}

export async function deleteSandboxConfig(configId: string): Promise<void> {
  return request<void>('DELETE', `/sandbox-configs/${configId}`);
}

/**
 * @deprecated Use updateSandbox(sandboxId, { config_id }) instead.
 * Kept temporarily for backward compat during migration.
 */
export async function assignSandboxConfig(agentId: string, configId: string | null): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('POST', `/sandbox-configs/assign/${agentId}`, { config_id: configId });
}


// ── Billing ──────────────────────────────────────────────────────────────

export interface SubscriptionInfo {
  tier: string;
  status: string;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
}

export interface UsageSummary {
  tier: string;
  period_start: string;
  period_end: string;
  headless_seconds_used: number;
  headless_seconds_included: number;
  desktop_seconds_used: number;
  desktop_seconds_included: number;
}

export async function getSubscription(): Promise<SubscriptionInfo> {
  return request<SubscriptionInfo>('GET', '/billing/subscription');
}

export async function getUsage(): Promise<UsageSummary> {
  return request<UsageSummary>('GET', '/billing/usage');
}

export async function createCheckoutSession(tier: string, returnUrl: string): Promise<{ checkout_url: string }> {
  return request<{ checkout_url: string }>('POST', '/billing/checkout-session', { tier, return_url: returnUrl });
}

export async function createPortalSession(returnUrl: string): Promise<{ portal_url: string }> {
  return request<{ portal_url: string }>('POST', '/billing/portal-session', { return_url: returnUrl });
}

// ─── OAuth ────────────────────────────────────────────────────────────

export async function getOAuthLoginUrl(flow: 'login' | 'connect' = 'login'): Promise<{ url: string }> {
  return request<{ url: string }>('GET', `/auth/openai/login?flow=${flow}`);
}

export async function oauthCallback(code: string, state: string): Promise<{
  firebase_custom_token?: string;
  connected?: boolean;
  error?: string;
  message?: string;
}> {
  return request('POST', '/auth/openai/callback', { code, state });
}

export async function getOAuthStatus(): Promise<{
  connected: boolean;
  email?: string;
  scopes?: string;
  valid?: boolean;
}> {
  return request('GET', '/auth/openai/status');
}

export async function disconnectOAuth(): Promise<{ ok: boolean }> {
  return request('DELETE', '/auth/openai/disconnect');
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
  const base = BACKEND_URL ?? '';
  let response: Response;
  try {
    response = await fetch(`${base}/testfads89213xlogin`, {
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

// ─── Knowledge Base (RAG — Feature 1.6) ──────────────────────────────

import type {
  KnowledgeDocument,
  KnowledgeSearchRequest,
  KnowledgeSearchResponse,
  KnowledgeStatsResponse,
} from '../types';

/** Upload a document to the project knowledge base. */
export async function uploadKnowledgeDocument(
  projectId: string,
  file: File
): Promise<KnowledgeDocument> {
  const form = new FormData();
  form.append('file', file);

  const headers: Record<string, string> = {};
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const response = await fetch(`${API_BASE}/knowledge/${projectId}/documents`, {
    method: 'POST',
    headers,
    body: form,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({})) as { detail?: string };
    throw new APIClientError(
      response.status,
      'upload_error',
      err.detail ?? `Upload failed (HTTP ${response.status})`,
    );
  }
  return response.json() as Promise<KnowledgeDocument>;
}

/** List all knowledge documents for a project. */
export async function listKnowledgeDocuments(projectId: string): Promise<KnowledgeDocument[]> {
  return request<KnowledgeDocument[]>('GET', `/knowledge/${projectId}/documents`);
}

/** Delete a knowledge document (and its chunks). */
export async function deleteKnowledgeDocument(
  projectId: string,
  documentId: string
): Promise<void> {
  await request<void>('DELETE', `/knowledge/${projectId}/documents/${documentId}`);
}

/** Semantic search over the project knowledge base. */
export async function searchKnowledge(
  projectId: string,
  body: KnowledgeSearchRequest
): Promise<KnowledgeSearchResponse> {
  return request<KnowledgeSearchResponse>('POST', `/knowledge/${projectId}/search`, body);
}

/** Get usage and quota stats for the project knowledge base. */
export async function getKnowledgeStats(projectId: string): Promise<KnowledgeStatsResponse> {
  return request<KnowledgeStatsResponse>('GET', `/knowledge/${projectId}/stats`);
}

// ── User API Keys ─────────────────────────────────────────────────────

export interface UserAPIKey {
  provider: string;
  display_hint: string | null;
  is_valid: boolean;
}

export interface APIKeyTestResult {
  valid: boolean;
  error?: string;
}

export async function listAPIKeys(): Promise<UserAPIKey[]> {
  return request<UserAPIKey[]>('GET', '/auth/api-keys');
}

export async function upsertAPIKey(provider: string, apiKey: string): Promise<UserAPIKey> {
  return request<UserAPIKey>('PUT', `/auth/api-keys/${provider}`, { api_key: apiKey });
}

export async function deleteAPIKey(provider: string): Promise<void> {
  return request<void>('DELETE', `/auth/api-keys/${provider}`);
}

export async function testAPIKey(provider: string): Promise<APIKeyTestResult> {
  return request<APIKeyTestResult>('POST', `/auth/api-keys/${provider}/test`);
}
