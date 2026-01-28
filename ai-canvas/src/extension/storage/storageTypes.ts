import type { Entity, EntityId, RepoIndex } from "src/shared/types";

export type WorkspaceEdge = {
  id: string;
  type: "contains" | "depends_on" | "implements" | "verifies";
  from: EntityId;
  to: EntityId;
};

export type WorkspaceState = {
  version: number;
  entities: Entity[];
  edges: WorkspaceEdge[];
  updated_at: string;
};

export type CacheState = {
  version: number;
  repo_index?: RepoIndex;
  updated_at: string;
};

export type StorageError = {
  code: string;
  message: string;
};

export type WorkspaceStore = {
  loadWorkspaceState: (root: string) => Promise<WorkspaceState | null>;
  saveWorkspaceState: (root: string, state: WorkspaceState) => Promise<void>;
};

export type CacheStore = {
  loadCache: (root: string) => Promise<CacheState | null>;
  saveCache: (root: string, cache: CacheState) => Promise<void>;
};
