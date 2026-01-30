import type { Entity } from '../../shared/types/entities';
import type { CanvasLayout } from '../../shared/types/rpc';

export interface WorkspaceState {
  entities: Entity[];
  canvas?: CanvasLayout;
}

export interface CacheState {
  version?: number;
  [key: string]: unknown;
}

export class StorageError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly cause?: unknown
  ) {
    super(message);
    this.name = 'StorageError';
  }
}
