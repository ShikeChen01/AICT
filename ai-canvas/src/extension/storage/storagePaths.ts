import * as path from "node:path";

export const getWorkspaceFilePath = (root: string): string =>
  path.resolve(root, ".vibecanvas.json");

export const getCacheFilePath = (root: string): string =>
  path.resolve(root, ".vibecanvas.cache.json");
