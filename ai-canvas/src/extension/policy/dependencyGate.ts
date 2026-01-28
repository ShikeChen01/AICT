import type { UnifiedDiff } from "src/shared/types/diff";

export type DependencyChange = {
  path: string;
  kind: "manifest" | "lockfile";
};

const MANIFEST_FILES = ["package.json", "pyproject.toml", "requirements.txt"];
const LOCK_FILES = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml"];

export class DependencyGate {
  detectDependencyChanges(diff: UnifiedDiff): DependencyChange[] {
    return detectDependencyChanges(diff);
  }
}

export const detectDependencyChanges = (diff: UnifiedDiff): DependencyChange[] => {
  const changes: DependencyChange[] = [];

  for (const file of diff.files) {
    const filename = file.new_path ?? file.old_path;
    const lower = filename.toLowerCase();

    if (MANIFEST_FILES.some((entry) => lower.endsWith(entry))) {
      changes.push({ path: filename, kind: "manifest" });
      continue;
    }

    if (LOCK_FILES.some((entry) => lower.endsWith(entry))) {
      changes.push({ path: filename, kind: "lockfile" });
    }
  }

  return changes;
};
