import fs from "node:fs/promises";
import { z } from "zod";
import { EntitySchema } from "../../shared/schemas/entitySchema";
import type { WorkspaceState } from "./storageTypes";
import { StorageError } from "./storageTypes";
import { getWorkspaceFilePath } from "./storagePaths";

const WorkspaceStateSchema = z.object({
  version: z.number().int().default(1),
  entities: z.array(EntitySchema),
});

export async function loadWorkspaceState(root: string): Promise<WorkspaceState> {
  const filePath = getWorkspaceFilePath(root);
  try {
    const raw = await fs.readFile(filePath, "utf8");
    const parsed = JSON.parse(raw);
    return WorkspaceStateSchema.parse(parsed);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return { version: 1, entities: [] };
    }
    if (error instanceof Error) {
      throw new StorageError("invalid_workspace", error.message);
    }
    throw error;
  }
}

export async function saveWorkspaceState(root: string, state: WorkspaceState): Promise<void> {
  const filePath = getWorkspaceFilePath(root);
  const tempPath = `${filePath}.tmp`;
  const payload = JSON.stringify(state, null, 2);
  await fs.writeFile(tempPath, payload, "utf8");
  await fs.rename(tempPath, filePath);
}
