import * as path from 'path';

const WORKSPACE_FILE = '.vibecanvas.json';
const CACHE_FILE = '.vibecanvas.cache.json';

/**
 * Resolve absolute path to workspace state file.
 */
export function getWorkspaceFilePath(root: string): string {
  return path.resolve(root, WORKSPACE_FILE);
}

/**
 * Resolve absolute path to cache file.
 */
export function getCacheFilePath(root: string): string {
  return path.resolve(root, CACHE_FILE);
}
