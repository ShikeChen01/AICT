import type { EntityId } from "src/shared/types/entities";

type ContextFile = {
  path: string;
  content: string;
  byte_size: number;
  mime_type?: string;
};

type ContextLog = {
  source: string;
  content: string;
  truncated?: boolean;
};

type ContextBundle = {
  id: string;
  scope_id: EntityId;
  files: ContextFile[];
  logs: ContextLog[];
  created_at: string;
  byte_size: number;
  token_estimate?: number;
};

export type { ContextBundle, ContextFile, ContextLog };
