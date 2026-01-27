export interface ContextFile {
  path: string;
  content: string;
}

export interface ContextLog {
  source: string;
  text: string;
}

export interface ContextBundle {
  scopeId?: string;
  files: ContextFile[];
  logs: ContextLog[];
  summaries: string[];
}
