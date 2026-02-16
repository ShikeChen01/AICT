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
  | 'in_review'
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

export type AgentRole = 'gm' | 'om' | 'manager' | 'engineer';
export type AgentStatus = 'sleeping' | 'active' | 'busy';

export interface Agent {
  id: UUID;
  project_id: UUID;
  role: AgentRole;
  display_name: string;
  model: string;
  status: AgentStatus;
  current_task_id: UUID | null;
  sandbox_id: string | null;
  sandbox_persist: boolean;
  priority: number; // 0=GM/Manager, 1=Engineer
  created_at: string;
  updated_at: string;
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
  open_ticket_count: number;
  task_queue: AgentTaskQueueItem[];
}

// ─── Chat ────────────────────────────────────────────────────────────

export type ChatRole = 'user' | 'gm' | 'manager';

export interface ChatMessage {
  id: UUID;
  project_id: UUID;
  role: ChatRole;
  content: string;
  attachments: unknown[] | null;
  created_at: string;
}

export interface ChatMessageCreate {
  content: string;
  attachments?: unknown[] | null;
}

export interface SendChatMessageResponse extends ChatMessage {
  user_message?: ChatMessage | null;
}

// ─── Ticket ──────────────────────────────────────────────────────────

export type TicketType = 'task_assignment' | 'question' | 'help' | 'issue' | 'abort';
export type TicketStatus = 'open' | 'closed';

export interface TicketMessage {
  id: UUID;
  ticket_id: UUID;
  from_agent_id: UUID | null;
  from_user_id: UUID | null;
  content: string;
  created_at: string;
}

export interface Ticket {
  id: UUID;
  project_id: UUID;
  from_agent_id: UUID;
  to_agent_id: UUID;
  header: string;
  ticket_type: TicketType;
  critical: number;
  urgent: number;
  status: TicketStatus;
  created_at: string;
  closed_at: string | null;
  closed_by_id: UUID | null;
  messages: TicketMessage[];
}

export interface TicketCreate {
  to_agent_id: UUID;
  header: string;
  ticket_type: TicketType;
  critical?: number;
  urgent?: number;
  initial_message?: string | null;
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
  | 'chat_message'
  | 'gm_status'
  | 'task_created'
  | 'task_update'
  | 'agent_status'
  | 'workflow_update'
  | 'agent_log'
  | 'sandbox_log'
  | 'job_started'
  | 'job_progress'
  | 'job_completed'
  | 'job_failed'
  | 'ticket_created'
  | 'ticket_reply'
  | 'ticket_closed'
  | 'mission_aborted';

export interface WSEvent<T = unknown> {
  type: WSEventType;
  data: T;
}

export interface WSChatMessageEvent {
  type: 'chat_message';
  data: ChatMessage;
}

export interface WSGMStatusEvent {
  type: 'gm_status';
  data: {
    status: 'available' | 'busy';
  };
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

export interface JobEventData {
  job_id: UUID;
  project_id: UUID;
  task_id: UUID;
  agent_id: UUID;
  status: 'started' | 'progress' | 'completed' | 'failed';
  message?: string | null;
  result?: string | null;
  error?: string | null;
  pr_url?: string | null;
  tool_name?: string | null;
  tool_args?: Record<string, unknown> | null;
}

export interface TicketEventData {
  ticket_id: UUID;
  project_id: UUID;
  from_agent_id: UUID | null;
  from_user_id: UUID | null;
  to_agent_id: UUID;
  header: string;
  ticket_type: TicketType;
  message: string | null;
}

// ─── API Response ────────────────────────────────────────────────────

export interface APIError {
  error_type: string;
  message: string;
  detail?: unknown;
}
