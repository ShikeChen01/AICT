import * as fs from "node:fs/promises";
import * as path from "node:path";
import type { ContextBundle, ContextFile } from "src/shared/types";
import type { WorkspaceState } from "src/extension/storage/storageTypes";
import type { RepoIndex } from "src/shared/types/rpc";

// Context packager: builds a size-capped bundle of files for provider prompts.
export type ContextPackagerInput = {
  root: string;
  scopeId: string;
  workspace?: WorkspaceState | null;
  repoIndex?: RepoIndex;
  includeLogs?: boolean;
  byteLimit?: number;
};

const resolveFileCandidates = (input: ContextPackagerInput): string[] => {
  const candidates: string[] = [];

  const workspace = input.workspace;
  if (workspace) {
    const entitiesById = new Map(workspace.entities.map((entity) => [entity.id, entity]));
    const scope = entitiesById.get(input.scopeId);

    const collectFromEntity = (entityId: string): void => {
      const entity = entitiesById.get(entityId);
      if (!entity) {
        return;
      }

      if (entity.type === "block" && entity.path) {
        candidates.push(entity.path);
      }

      entity.children?.forEach((childId) => collectFromEntity(childId));
    };

    if (scope) {
      collectFromEntity(scope.id);
    }
  }

  if (candidates.length === 0 && input.repoIndex) {
    const root = path.resolve(input.root);
    for (const file of input.repoIndex.files) {
      if (file.startsWith(root)) {
        candidates.push(file);
      }
      if (candidates.length >= 25) {
        break;
      }
    }
  }

  const root = path.resolve(input.root);
  const normalized = candidates.map((candidate) =>
    path.isAbsolute(candidate) ? candidate : path.resolve(root, candidate),
  );
  return Array.from(new Set(normalized));
};

const readFileWithLimit = async (filePath: string, limit: number): Promise<ContextFile | null> => {
  try {
    const content = await fs.readFile(filePath, "utf8");
    const byteSize = Buffer.byteLength(content, "utf8");
    if (byteSize > limit) {
      return null;
    }

    return {
      path: filePath,
      content,
      byte_size: byteSize,
      mime_type: "text/plain",
    };
  } catch {
    return null;
  }
};

export const buildContextBundle = async (input: ContextPackagerInput): Promise<ContextBundle> => {
  const byteLimit = input.byteLimit ?? 80_000;
  const files: ContextFile[] = [];
  let totalBytes = 0;

  const candidates = resolveFileCandidates(input);
  for (const candidate of candidates) {
    if (totalBytes >= byteLimit) {
      break;
    }

    const remaining = byteLimit - totalBytes;
    const file = await readFileWithLimit(candidate, remaining);
    if (!file) {
      continue;
    }

    files.push(file);
    totalBytes += file.byte_size;
  }

  return {
    id: `ctx_${Date.now()}`,
    scope_id: input.scopeId,
    files,
    logs: [],
    created_at: new Date().toISOString(),
    byte_size: totalBytes,
    token_estimate: Math.ceil(totalBytes / 4),
  };
};
