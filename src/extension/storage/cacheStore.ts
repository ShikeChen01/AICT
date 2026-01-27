import fs from "node:fs/promises";
import { z } from "zod";
import type { CacheState } from "./storageTypes";
import { StorageError } from "./storageTypes";
import { getCacheFilePath } from "./storagePaths";

const CacheStateSchema = z.object({
  version: z.number().int().default(1),
  repoIndex: z.unknown().optional(),
});

export async function loadCache(root: string): Promise<CacheState> {
  const filePath = getCacheFilePath(root);
  try {
    const raw = await fs.readFile(filePath, "utf8");
    const parsed = JSON.parse(raw);
    return CacheStateSchema.parse(parsed);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return { version: 1 };
    }
    if (error instanceof Error) {
      throw new StorageError("invalid_cache", error.message);
    }
    throw error;
  }
}

export async function saveCache(root: string, state: CacheState): Promise<void> {
  const filePath = getCacheFilePath(root);
  const tempPath = `${filePath}.tmp`;
  const payload = JSON.stringify(state, null, 2);
  await fs.writeFile(tempPath, payload, "utf8");
  await fs.rename(tempPath, filePath);
}
