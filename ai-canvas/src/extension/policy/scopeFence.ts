import * as path from "node:path";

export type ScopeFenceOptions = {
  root: string;
  allow: string[];
  deny?: string[];
  maxFiles?: number;
};

export class ScopeFence {
  private readonly root: string;
  private readonly allow: string[];
  private readonly deny: string[];
  private readonly maxFiles?: number;

  constructor(options: ScopeFenceOptions) {
    this.root = path.resolve(options.root);
    this.allow = options.allow.map((entry) => path.resolve(this.root, entry));
    this.deny = (options.deny ?? []).map((entry) => path.resolve(this.root, entry));
    this.maxFiles = options.maxFiles;
  }

  isPathAllowed(candidate: string): boolean {
    const resolved = path.resolve(this.root, candidate);
    if (this.deny.some((entry) => resolved.startsWith(entry))) {
      return false;
    }
    if (this.allow.length === 0) {
      return true;
    }
    return this.allow.some((entry) => resolved.startsWith(entry));
  }

  enforceMaxFiles(paths: string[]): boolean {
    if (!this.maxFiles) {
      return true;
    }
    return paths.length <= this.maxFiles;
  }
}

export const normalizeScope = (scope: string | string[]): string[] => {
  if (Array.isArray(scope)) {
    return scope.map((entry) => entry.trim()).filter(Boolean);
  }
  return scope.split(",").map((entry) => entry.trim()).filter(Boolean);
};

export const isPathAllowed = (candidate: string, fence?: ScopeFence): boolean => {
  if (!fence) {
    return true;
  }
  return fence.isPathAllowed(candidate);
};
