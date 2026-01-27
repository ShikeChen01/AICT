export type DependencyChangeType = "manifest" | "lockfile";

export interface DependencyChange {
  path: string;
  type: DependencyChangeType;
}

const MANIFEST_FILES = new Set([
  "package.json",
  "pyproject.toml",
  "requirements.txt",
  "Pipfile",
  "Pipfile.lock",
]);

const LOCK_FILES = new Set([
  "package-lock.json",
  "yarn.lock",
  "pnpm-lock.yaml",
  "poetry.lock",
  "Pipfile.lock",
]);

function normalizeDiffPath(rawPath: string): string {
  return rawPath.replace(/^a\//, "").replace(/^b\//, "").trim();
}

export function detectDependencyChanges(diff: string): DependencyChange[] {
  const changes: DependencyChange[] = [];
  const lines = diff.split(/\r?\n/);
  for (const line of lines) {
    if (!line.startsWith("+++ ") && !line.startsWith("--- ") && !line.startsWith("diff --git ")) {
      continue;
    }
    let candidate = "";
    if (line.startsWith("diff --git ")) {
      const parts = line.split(" ");
      candidate = parts[2] || "";
    } else {
      candidate = line.slice(4);
    }
    const path = normalizeDiffPath(candidate);
    const fileName = path.split("/").pop() ?? path;
    if (MANIFEST_FILES.has(fileName)) {
      changes.push({ path, type: "manifest" });
      continue;
    }
    if (LOCK_FILES.has(fileName)) {
      changes.push({ path, type: "lockfile" });
    }
  }
  return changes;
}
