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
  | 'done';

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

export type AgentRole = 'gm' | 'om' | 'engineer';
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
  priority: number; // 0=GM, 1=OM, 2=Engineer
  created_at: string;
  updated_at: string;
}

// ─── Chat ────────────────────────────────────────────────────────────

export type ChatRole = 'user' | 'gm';

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

// ─── Ticket ──────────────────────────────────────────────────────────

export type TicketType = 'task_assignment' | 'question' | 'help' | 'issue';
export type TicketStatus = 'open' | 'closed';

export interface TicketMessage {
  id: UUID;
  ticket_id: UUID;
  from_agent_id: UUID;
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

// ─── Project ─────────────────────────────────────────────────────────

export interface Project {
  id: UUID;
  name: string;
  description: string | null;
  spec_repo_path: string;
  code_repo_url: string;
  code_repo_path: string;
  created_at: string;
  updated_at: string;
}

// ─── WebSocket Events ────────────────────────────────────────────────

export type WSEventType =
  | 'chat_message'
  | 'gm_status'
  | 'task_created'
  | 'task_update'
  | 'agent_status';

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
    agent_id: UUID;
    status: AgentStatus;
  };
}

// ─── API Response ────────────────────────────────────────────────────

export interface APIError {
  error_type: string;
  message: string;
  detail?: unknown;
}
