import * as fs from "node:fs/promises";
import * as path from "node:path";
import { z } from "zod";
import { EntitySchema } from "src/shared/schemas/entitySchema";
import type { WorkspaceState } from "src/extension/storage/storageTypes";
import { getWorkspaceFilePath } from "src/extension/storage/storagePaths";

const WorkspaceEdgeSchema = z.object({
  id: z.string().min(1),
  type: z.enum(["contains", "depends_on", "implements", "verifies"]),
  from: z.string().min(1),
  to: z.string().min(1),
});

const WorkspaceStateSchema: z.ZodType<WorkspaceState> = z.object({
  version: z.number().int(),
  entities: z.array(EntitySchema),
  edges: z.array(WorkspaceEdgeSchema),
  updated_at: z.string().min(1),
});

const writeAtomic = async (filePath: string, payload: string): Promise<void> => {
  const tempPath = `${filePath}.tmp`;
  await fs.writeFile(tempPath, payload, "utf8");
  await fs.rename(tempPath, filePath);
};

export const loadWorkspaceState = async (root: string): Promise<WorkspaceState | null> => {
  const filePath = getWorkspaceFilePath(root);
  try {
    const raw = await fs.readFile(filePath, "utf8");
    const parsed = WorkspaceStateSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) {
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
};

export const saveWorkspaceState = async (root: string, state: WorkspaceState): Promise<void> => {
  const filePath = getWorkspaceFilePath(root);
  const serialized = JSON.stringify(state, null, 2);
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await writeAtomic(filePath, serialized);
};

export const workspaceStore = {
  loadWorkspaceState,
  saveWorkspaceState,
};
