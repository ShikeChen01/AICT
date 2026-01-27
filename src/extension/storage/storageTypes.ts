import type { Entity } from "../../shared/types";

export interface WorkspaceState {
  version: number;
  entities: Entity[];
}

export interface CacheState {
  version: number;
  repoIndex?: unknown;
}

export class StorageError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}
