import path from "node:path";

export function getWorkspaceFilePath(root: string): string {
  return path.resolve(root, ".vibecanvas.json");
}

export function getCacheFilePath(root: string): string {
  return path.resolve(root, ".vibecanvas.cache.json");
}
