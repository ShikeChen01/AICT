import * as fs from "node:fs/promises";
import * as path from "node:path";
import { z } from "zod";
import { getCacheFilePath } from "src/extension/storage/storagePaths";
import type { CacheState } from "src/extension/storage/storageTypes";
import { RepoIndexSchema } from "src/shared/schemas/rpcSchema";

const CacheStateSchema: z.ZodType<CacheState> = z.object({
  version: z.number().int(),
  repo_index: RepoIndexSchema.optional(),
  updated_at: z.string().min(1),
});

const writeAtomic = async (filePath: string, payload: string): Promise<void> => {
  const tempPath = `${filePath}.tmp`;
  await fs.writeFile(tempPath, payload, "utf8");
  await fs.rename(tempPath, filePath);
};

export const loadCache = async (root: string): Promise<CacheState | null> => {
  const filePath = getCacheFilePath(root);
  try {
    const raw = await fs.readFile(filePath, "utf8");
    const parsed = CacheStateSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) {
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
};

export const saveCache = async (root: string, cache: CacheState): Promise<void> => {
  const filePath = getCacheFilePath(root);
  const serialized = JSON.stringify(cache, null, 2);
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await writeAtomic(filePath, serialized);
};

export const cacheStore = {
  loadCache,
  saveCache,
};
