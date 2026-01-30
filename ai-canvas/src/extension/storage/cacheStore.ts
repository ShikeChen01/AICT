import * as fs from 'fs/promises';
import { getCacheFilePath } from './storagePaths';
import type { CacheState } from './storageTypes';
import { StorageError } from './storageTypes';

const defaultCache: CacheState = { version: 1 };

/**
 * Load cache from .vibecanvas.cache.json. Returns default if missing.
 */
export async function loadCache(root: string): Promise<CacheState> {
  const filePath = getCacheFilePath(root);
  try {
    const raw = await fs.readFile(filePath, 'utf-8');
    const json = JSON.parse(raw) as CacheState;
    return json ?? defaultCache;
  } catch (err) {
    const nodeErr = err as NodeJS.ErrnoException;
    if (nodeErr?.code === 'ENOENT') {
      return defaultCache;
    }
    throw new StorageError(
      `Failed to load cache: ${nodeErr?.message ?? err}`,
      'LOAD_FAILED',
      err
    );
  }
}

/**
 * Write cache to .vibecanvas.cache.json.
 */
export async function saveCache(root: string, cache: CacheState): Promise<void> {
  const filePath = getCacheFilePath(root);
  try {
    await fs.writeFile(filePath, JSON.stringify(cache, null, 2), 'utf-8');
  } catch (err) {
    const nodeErr = err as NodeJS.ErrnoException;
    throw new StorageError(
      `Failed to save cache: ${nodeErr?.message ?? err}`,
      'SAVE_FAILED',
      err
    );
  }
}
