/**
 * AICT Frontend Types
 * Matches backend Pydantic schemas and SQLAlchemy models
 */

// ─── Common ──────────────────────────────────────────────────────────

export type UUID = string;

// ─── Task ────────────────────────────────────────────────────────────

export type TaskStatus =
  | 'backlog'
  | 'specifying'
  | 'assigned'
  | 'in_progress'
  | 'review'
  | 'done'
  | 'aborted';

export interface Task {
  id: UUID;
  project_id: UUID;
  title: string;
  description: string | null;
  status: TaskStatus;
  critical: number; // 0-10
  urgent: number; // 0-10
  assigned_agent_id: UUID | null;
  module_path: string | null;
  git_branch: string | null;
  pr_url: string | null;
  parent_task_id: UUID | null;
  created_by_id: UUID | null;
  abort_reason: string | null;
  abort_documentation: string | null;
  aborted_by_id: UUID | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  description?: string | null;
  status?: TaskStatus;
  critical?: number;
  urgent?: number;
  module_path?: string | null;
  parent_task_id?: UUID | null;
}

export interface TaskUpdate {
  title?: string | null;
  description?: string | null;
  status?: TaskStatus | null;
  critical?: number | null;
  urgent?: number | null;
  assigned_agent_id?: UUID | null;
  module_path?: string | null;
  git_branch?: string | null;
  pr_url?: string | null;
}

// ─── Agent ───────────────────────────────────────────────────────────

export type AgentRole = 'manager' | 'cto' | 'engineer';
export type AgentStatus = 'sleeping' | 'active' | 'busy';
export type BaseRole = 'manager' | 'cto' | 'worker';

export interface TokenAllocations {
  incoming_msg_tokens?: number;
  memory_pct?: number;
  past_session_pct?: number;
  current_session_pct?: number;
}

export interface Agent {
  id: UUID;
  project_id: UUID;
  template_id: UUID | null;
  role: AgentRole;
  display_name: string;
  model: string;
  provider: string | null;
  thinking_enabled: boolean;
  status: AgentStatus;
  current_task_id: UUID | null;
  sandbox_id: string | null;
  sandbox_persist: boolean;
  sandbox_config_id: UUID | null;
  memory?: Record<string, unknown> | null;
  token_allocations?: TokenAllocations | null;
  created_at: string;
  updated_at: string;
}

// ─── Agent Templates ─────────────────────────────────────────────────

export interface AgentTemplate {
  id: UUID;
  project_id: UUID;
  name: string;
  description: string | null;
  base_role: BaseRole;
  model: string;
  provider: string | null;
  thinking_enabled: boolean;
  sandbox_template: string | null;
  knowledge_sources: Record<string, unknown> | unknown[] | null;
  trigger_config: Record<string, unknown> | null;
  cost_limits: Record<string, unknown> | null;
  is_system_default: boolean;
}

export interface CreateAgentTemplate {
  name: string;
  description?: string;
  base_role?: BaseRole;
  model: string;
  provider?: string | null;
  thinking_enabled?: boolean;
  sandbox_template?: string | null;
  knowledge_sources?: Record<string, unknown> | unknown[] | null;
  trigger_config?: Record<string, unknown> | null;
  cost_limits?: Record<string, unknown> | null;
}

export interface UpdateAgentTemplate {
  name?: string;
  model?: string;
  provider?: string | null;
  thinking_enabled?: boolean;
}

// ─── Prompt Blocks ───────────────────────────────────────────────────

export interface PromptBlockConfig {
  id: UUID;
  template_id: UUID | null;
  agent_id: UUID | null;
  block_key: string;
  content: string;
  position: number;
  enabled: boolean;
}

export interface PromptBlockConfigItem {
  block_key: string;
  content: string;
  position: number;
  enabled: boolean;
}

export interface UpdateAgentRequest {
  model?: string;
  provider?: string | null;
  thinking_enabled?: boolean;
  display_name?: string;
  token_allocations?: TokenAllocations | null;
}

export interface BlockMetaInfo {
  kind: 'system' | 'conditional' | 'conversation';
  max_chars: number | null;
  truncation: string;
}

export interface PromptMeta {
  context_window_tokens: number;
  total_budget_tokens: number;  // context_window + image_reserve (image reserve outside 200k)
  static_overhead_tokens: number;
  dynamic_pool_tokens: number;
  // Dynamic section budgets
  memory_budget_tokens: number;
  past_session_budget_tokens: number;
  current_session_budget_tokens: number;
  // Static section details
  system_prompt_tokens: number;
  tool_schema_tokens: number;
  incoming_msg_budget_tokens: number;
  // Effective allocation percentages (agent overrides or system defaults)
  memory_pct: number;
  past_session_pct: number;
  current_session_pct: number;
  // System defaults (for reset)
  default_memory_pct: number;
  default_past_session_pct: number;
  default_current_session_pct: number;
  default_incoming_msg_tokens: number;
  // Image input budget (outside context_window; total_budget = context_window + image_reserve)
  image_tokens_per_image: number;      // per-image token cost (0 = not vision-capable)
  image_default_max_images: number;    // system-wide default cap
  image_effective_max_images: number;  // agent override or system default
  image_reserve_tokens: number;        // total = tokens_per_image × effective_max_images
  model_supports_vision: boolean;      // true if model accepts image inputs
  // Registry
  block_registry: Record<string, BlockMetaInfo>;
}

// ─── Tool Config ─────────────────────────────────────────────────────────

export interface ToolConfig {
  id: UUID;
  agent_id: UUID | null;
  template_id: UUID | null;
  tool_name: string;
  description: string;
  detailed_description: string | null;
  input_schema: Record<string, unknown>;
  allowed_roles: string[];
  enabled: boolean;
  position: number;
  estimated_tokens: number;
  source: 'native' | 'mcp';
  mcp_server_id: UUID | null;
}

export interface ToolConfigUpdateItem {
  tool_name: string;
  description: string;
  detailed_description?: string | null;
  enabled: boolean;
  position: number;
}

export interface ToolConfigMeta {
  total_tools: number;
  enabled_tools: number;
  total_tokens: number;
  max_tokens: number;
  budget_pct_used: number;
  context_window_tokens: number;
}

// ─── MCP Server Configs ────────────────────────────────────────────────

export interface McpServer {
  id: UUID;
  agent_id: UUID;
  name: string;
  url: string;
  has_api_key: boolean;
  headers: Record<string, string> | null;
  enabled: boolean;
  status: 'connected' | 'disconnected' | 'error';
  status_detail: string | null;
  tool_count: number;
}

export interface McpServerCreate {
  name: string;
  url: string;
  api_key?: string | null;
  headers?: Record<string, string> | null;
}

export interface McpServerUpdate {
  name?: string;
  url?: string;
  api_key?: string | null;
  headers?: Record<string, string> | null;
  enabled?: boolean;
}

export interface McpSyncResult {
  status: string;
  tools_discovered: number;
  tools: Array<{
    tool_name: string;
    description: string;
    input_schema: Record<string, unknown>;
    enabled: boolean;
  }>;
}

export interface AgentTaskQueueItem {
  id: UUID;
  title: string;
  status: TaskStatus;
  critical: number;
  urgent: number;
  module_path: string | null;
  updated_at: string;
}

export interface AgentStatusWithQueue extends Agent {
  queue_size: number;
  pending_message_count?: number;
  task_queue: AgentTaskQueueItem[];
}

// ─── Agent Sessions (NEW) ──────────────────────────────────────────────

export type AgentSessionStatus = 'running' | 'completed' | 'force_ended' | 'error';
export type AgentSessionEndReason =
  | 'normal_end'
  | 'max_iterations'
  | 'max_loopbacks'
  | 'interrupted'
  | 'aborted'
  | 'error'
  | null;

export interface AgentSession {
  id: UUID;
  agent_id: UUID;
  project_id: UUID;
  task_id: UUID | null;
  trigger_message_id: UUID | null;
  status: AgentSessionStatus;
  end_reason: AgentSessionEndReason;
  iteration_count: number;
  started_at: string;
  ended_at: string | null;
}

export interface AgentMessageLog {
  id: UUID;
  agent_id: UUID;
  session_id: UUID | null;
  project_id: UUID;
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_name: string | null;
  tool_input: Record<string, unknown> | null;
  tool_output: string | null;
  loop_iteration: number;
  created_at: string;
}

// ─── Project Settings ─────────────────────────────────────────────────

export interface ModelOverrides {
  manager?: string;
  cto?: string;
  engineer_junior?: string;
  engineer_intermediate?: string;
  engineer_senior?: string;
}

export interface PromptOverrides {
  manager?: string;
  cto?: string;
  engineer?: string;
}

export interface ProjectSettings {
  id: UUID;
  project_id: UUID;
  max_engineers: number;
  persistent_sandbox_count: number;
  // Phase 3
  model_overrides: ModelOverrides | null;
  prompt_overrides: PromptOverrides | null;
  // Phase 4: daily hard limits
  daily_token_budget: number;
  // Phase 4b: hourly rate limits + cost budget
  calls_per_hour_limit: number;
  tokens_per_hour_limit: number;
  daily_cost_budget_usd: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectSettingsUpdate {
  max_engineers?: number;
  persistent_sandbox_count?: number;
  // Phase 3
  model_overrides?: ModelOverrides | null;
  prompt_overrides?: PromptOverrides | null;
  // Phase 4
  daily_token_budget?: number;
  // Phase 4b
  calls_per_hour_limit?: number;
  tokens_per_hour_limit?: number;
  daily_cost_budget_usd?: number;
}

// ─── Project secrets (per-project tokens for agents) ───────────────────

export interface ProjectSecret {
  id: UUID;
  name: string;
  hint: string | null;
  created_at: string;
}

export interface ProjectSecretUpsert {
  name: string;
  value: string;
}

// ─── LLM Usage (Phase 4) ─────────────────────────────────────────────

export interface LLMUsageByModel {
  provider: string;
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface LLMUsageRollup {
  date_utc: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  by_model: LLMUsageByModel[];
}

export interface LLMHourlyRollup {
  window: string;
  total_calls: number;
  total_tokens: number;
  by_model: Omit<LLMUsageByModel, 'estimated_cost_usd'>[];
}

export interface LLMUsageCall {
  id: UUID;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  agent_id: UUID | null;
  session_id: UUID | null;
  created_at: string;
}

export interface ProjectUsageResponse {
  today: LLMUsageRollup;
  last_hour: LLMHourlyRollup;
  recent_calls: LLMUsageCall[];
}

// ─── Repository Memberships (Phase 2) ────────────────────────────────

export type MembershipRole = 'owner' | 'member' | 'viewer';

export interface RepositoryMembership {
  id: UUID;
  repository_id: UUID;
  user_id: UUID;
  role: MembershipRole;
  created_at: string;
}

// ─── Channel Messages (NEW — user-to-agent) ───────────────────────────

export type ChannelMessageType = 'normal' | 'system';

export interface ChannelMessage {
  id: UUID;
  project_id: UUID;
  from_agent_id: UUID | null;
  target_agent_id: UUID | null;
  from_user_id: UUID | null;  // Phase 2: real user attribution
  content: string;
  message_type: ChannelMessageType;
  status: 'sent' | 'received';
  broadcast: boolean;
  created_at: string;
  // Phase 6: IDs of linked image attachments (empty for text-only messages)
  attachment_ids: string[];
}

export interface ChannelMessageSend {
  project_id: UUID;
  target_agent_id: UUID;
  content: string;
  // Phase 6: pre-uploaded attachment IDs to link to this message
  attachment_ids?: string[];
}

// ─── Attachments (Phase 6) ───────────────────────────────────────────

export interface Attachment {
  id: UUID;
  project_id: UUID;
  uploaded_by_user_id: UUID | null;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

// ─── Repository ──────────────────────────────────────────────────────

export interface Repository {
  id: UUID;
  owner_id?: UUID | null;
  name: string;
  description: string | null;
  spec_repo_path: string;
  code_repo_url: string;
  code_repo_path: string;
  created_at: string;
  updated_at: string;
}

export interface RepositoryCreate {
  name: string;
  description?: string | null;
  private?: boolean;
}

export interface RepositoryImport {
  name: string;
  description?: string | null;
  code_repo_url: string;
}

export interface RepositoryUpdate {
  name?: string | null;
  description?: string | null;
  code_repo_url?: string | null;
}

// Backward-compatible aliases for existing component code.
export type Project = Repository;
export type ProjectCreate = RepositoryCreate;
export type ProjectImport = RepositoryImport;
export type ProjectUpdate = RepositoryUpdate;

export interface UserProfile {
  id: UUID;
  email: string;
  display_name: string | null;
  github_token_set: boolean;
  created_at: string;
  updated_at: string;
}

// ─── Agent Context (Inspector) ────────────────────────────────────────

export interface AgentTool {
  name: string;
  description: string | null;
}

export interface AgentContext {
  id: UUID;
  role: AgentRole;
  display_name: string;
  model: string;
  status: AgentStatus;
  system_prompt: string | null;
  available_tools: AgentTool[];
  recent_messages: Record<string, unknown>[];
  sandbox_id: string | null;
  sandbox_active: boolean;
}

// ─── WebSocket Events ────────────────────────────────────────────────

export type WSEventType =
  | 'task_created'
  | 'task_update'
  | 'agent_status'
  | 'workflow_update'
  | 'agent_log'
  | 'sandbox_log'
  | 'backend_log'
  | 'backend_log_snapshot'
  // New stream events (Agent 2)
  | 'agent_text'
  | 'agent_tool_call'
  | 'agent_tool_result'
  | 'agent_message'
  | 'system_message'
  // Real-time LLM usage stream
  | 'usage_update'
  // Architecture documents (Phase 10)
  | 'document_updated'
  | 'agent_stopped';

export interface WSEvent<T = unknown> {
  type: WSEventType;
  data: T;
}

export interface WSTaskCreatedEvent {
  type: 'task_created';
  data: Task;
}

export interface WSTaskUpdateEvent {
  type: 'task_update';
  data: Task;
}

export interface WSAgentStatusEvent {
  type: 'agent_status';
  data: {
    id: UUID;
    project_id: UUID;
    role: AgentRole;
    display_name: string;
    status: AgentStatus;
    current_task_id: UUID | null;
  };
}

// ─── Workflow Events (Frontend V2) ────────────────────────────────────

export interface WorkflowUpdateData {
  project_id: UUID;
  thread_id: string;
  previous_node: string | null;
  current_node: string;
  node_status: 'started' | 'completed' | 'error';
  metadata?: Record<string, unknown>;
}

export interface WSWorkflowUpdateEvent {
  type: 'workflow_update';
  data: WorkflowUpdateData;
}

export interface AgentLogData {
  project_id: UUID;
  agent_id: UUID;
  agent_role: AgentRole;
  log_type: 'thought' | 'tool_call' | 'tool_result' | 'message' | 'error';
  content: string;
  tool_name?: string | null;
  tool_input?: Record<string, unknown> | null;
  tool_output?: string | null;
}

export interface WSAgentLogEvent {
  type: 'agent_log';
  data: AgentLogData;
}

export interface ActivityLogItem extends AgentLogData {
  id: string;
  timestamp: string;
}

export interface SandboxLogData {
  project_id: UUID;
  agent_id: UUID;
  sandbox_id: string;
  stream: 'stdout' | 'stderr';
  content: string;
}

export interface WSSandboxLogEvent {
  type: 'sandbox_log';
  data: SandboxLogData;
}

export interface BackendLogItem {
  seq: number;
  ts: string;
  level: string;
  logger: string;
  message: string;
}

export interface BackendLogSnapshotData {
  items: BackendLogItem[];
  latest_seq: number;
}

// ─── Agent Stream Events (NEW) ────────────────────────────────────────

export interface AgentTextData {
  agent_id: UUID;
  agent_role: AgentRole;
  content: string;
  session_id?: UUID | null;
  iteration?: number;
}

export interface AgentToolCallData {
  agent_id: UUID;
  agent_role: AgentRole;
  tool_name: string;
  tool_input: Record<string, unknown>;
  session_id?: UUID | null;
  iteration?: number;
}

export interface AgentToolResultData {
  agent_id: UUID;
  tool_name: string;
  output: string;
  success: boolean;
  session_id?: UUID | null;
  iteration?: number;
}

export interface AgentMessageData {
  id: UUID;
  from_agent_id: UUID;
  target_agent_id: UUID;
  content: string;
  message_type: ChannelMessageType;
  created_at?: string | null;
}

export interface SystemMessageData {
  content: string;
  created_at?: string | null;
}

export interface AgentMemoryResponse {
  memory: Record<string, unknown> | null;
}

export interface AgentInterruptRequest {
  reason: string;
}

export interface AgentInterruptResponse {
  message: string;
}

export interface AgentWakeRequest {
  message?: string | null;
}

export interface AgentWakeResponse {
  message: string;
}

// ─── LLM Usage Stream (real-time, Phase 4 WebSocket) ─────────────────

export interface UsageUpdateData {
  project_id: UUID;
  agent_id: UUID | null;
  model: string;
  provider: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  created_at: string;
}

// ─── Stream buffer (frontend) ──────────────────────────────────────────

export type StreamChunk =
  | { type: 'text'; content: string; timestamp: string }
  | { type: 'tool_call'; toolName: string; toolInput: Record<string, unknown>; timestamp: string }
  | { type: 'tool_result'; toolName: string; output: string; success: boolean; timestamp: string }
  | { type: 'message'; content: string; from: string; timestamp: string };

export interface AgentStreamBuffer {
  agentId: string;
  sessionId: string | null;
  chunks: StreamChunk[];
  isStreaming: boolean;
  lastActivity: number;
}

// ─── Architecture Documents ───────────────────────────────────────────

export interface ProjectDocument {
  id: UUID;
  project_id: UUID;
  doc_type: string;
  title: string | null;
  content: string | null;
  updated_by_agent_id: UUID | null;
  updated_by_user_id: UUID | null;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectDocumentSummary {
  id: UUID;
  project_id: UUID;
  doc_type: string;
  title: string | null;
  updated_by_agent_id: UUID | null;
  updated_by_user_id: UUID | null;
  current_version: number;
  updated_at: string;
}

export interface DocumentVersion {
  id: UUID;
  document_id: UUID;
  version_number: number;
  content: string | null;
  title: string | null;
  edited_by_agent_id: UUID | null;
  edited_by_user_id: UUID | null;
  edit_summary: string | null;
  created_at: string;
}

export interface DocumentVersionSummary {
  id: UUID;
  document_id: UUID;
  version_number: number;
  title: string | null;
  edited_by_agent_id: UUID | null;
  edited_by_user_id: UUID | null;
  edit_summary: string | null;
  created_at: string;
}

export interface DocumentEditRequest {
  content: string;
  title?: string | null;
  edit_summary?: string | null;
}

export interface DocumentUpdatedData {
  project_id: UUID;
  doc_type: string;
  title: string;
}

// ─── Sandbox Configs ──────────────────────────────────────────────────

export interface SandboxConfig {
  id: UUID;
  user_id: UUID;
  name: string;
  description: string | null;
  setup_script: string;
  os_image: string | null;
  created_at: string;
  updated_at: string;
}

export interface SandboxConfigCreate {
  name: string;
  description?: string | null;
  setup_script?: string;
  os_image?: string | null;
}

export interface SandboxConfigUpdate {
  name?: string;
  description?: string | null;
  setup_script?: string;
  os_image?: string | null;
}

// ── Sandbox types (v3 — DB-backed sandboxes) ─────────────────────────────

export interface Sandbox {
  id: string;
  project_id: string;
  agent_id: string | null;
  agent_name: string | null;
  agent_role: string | null;
  sandbox_config_id: string | null;
  orchestrator_sandbox_id: string;
  os_image: string;
  persistent: boolean;
  status: string;
  host: string | null;
  port: number;
  created_at: string | null;
  assigned_at: string | null;
}

export interface SandboxConnectionInfo {
  host: string;
  port: number;
  token: string;
  vnc_path: string;
  screen_path: string;
}

export interface SandboxSnapshot {
  id: string;
  sandbox_id: string;
  label: string | null;
  k8s_snapshot_name: string;
  os_image: string;
  created_at: string | null;
}

export interface SandboxClaimRequest {
  agent_id: string;
}

export interface SandboxUpdateRequest {
  persistent?: boolean;
  sandbox_config_id?: string | null;
}

export interface SandboxSnapshotRequest {
  label: string;
}

export interface SandboxRestoreRequest {
  snapshot_id: string;
}

// ─── API Response ────────────────────────────────────────────────────

export interface APIError {
  error_type: string;
  message: string;
  detail?: unknown;
}

// ─── Knowledge Base (RAG) ─────────────────────────────────────────────

export interface KnowledgeDocument {
  id: UUID;
  project_id: UUID;
  filename: string;
  file_type: string;
  mime_type: string;
  original_size_bytes: number;
  chunk_count: number;
  status: 'pending' | 'indexing' | 'indexed' | 'failed';
  error_message: string | null;
  indexed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeSearchRequest {
  query: string;
  limit?: number;
  similarity_threshold?: number;
}

export interface KnowledgeSearchResult {
  chunk_id: UUID;
  document_id: UUID;
  filename: string;
  file_type: string;
  chunk_index: number;
  text_content: string;
  similarity_score: number;
  metadata: Record<string, unknown> | null;
}

export interface KnowledgeSearchResponse {
  query: string;
  result_count: number;
  results: KnowledgeSearchResult[];
  duration_ms: number;
}

export interface KnowledgeStatsResponse {
  project_id: UUID;
  total_documents: number;
  indexed_documents: number;
  total_chunks: number;
  total_bytes: number;
  quota_documents: number;
  quota_bytes: number;
}
