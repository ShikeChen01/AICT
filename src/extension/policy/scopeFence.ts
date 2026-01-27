import path from "node:path";

export interface ScopeFenceOptions {
  root: string;
  allowedPaths: string[];
  forbiddenPaths?: string[];
  maxFiles?: number;
}

export class ScopeFence {
  readonly root: string;
  readonly allowedPaths: string[];
  readonly forbiddenPaths: string[];
  readonly maxFiles?: number;

  constructor(options: ScopeFenceOptions) {
    this.root = path.resolve(options.root);
    this.allowedPaths = normalizeScope(options.allowedPaths, this.root);
    this.forbiddenPaths = normalizeScope(options.forbiddenPaths ?? [], this.root);
    this.maxFiles = options.maxFiles;
  }
}

export function normalizeScope(paths: string[], root: string): string[] {
  const resolvedRoot = path.resolve(root);
  const normalized = new Set<string>();
  for (const entry of paths) {
    const resolved = path.resolve(resolvedRoot, entry);
    normalized.add(resolved);
  }
  return Array.from(normalized);
}

function isWithin(target: string, base: string): boolean {
  const relative = path.relative(base, target);
  return !!relative && !relative.startsWith("..") && !path.isAbsolute(relative);
}

export function isPathAllowed(targetPath: string, fence: ScopeFence): boolean {
  const resolved = path.resolve(fence.root, targetPath);
  const allowed = fence.allowedPaths.some((base) => resolved === base || isWithin(resolved, base));
  if (!allowed) {
    return false;
  }
  const forbidden = fence.forbiddenPaths.some((base) => resolved === base || isWithin(resolved, base));
  return !forbidden;
}
