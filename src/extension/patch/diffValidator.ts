import type { ScopeFence } from "../policy/scopeFence";
import { isPathAllowed } from "../policy/scopeFence";
import type { Patch, PatchFile, PatchHunk } from "./patchTypes";

export interface DiffValidationError {
  message: string;
  file?: string;
}

function normalizeDiffPath(rawPath: string): string {
  return rawPath.replace(/^a\//, "").replace(/^b\//, "").trim();
}

function parseUnifiedDiff(diff: string): Patch {
  const files: PatchFile[] = [];
  const lines = diff.split(/\r?\n/);
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.startsWith("--- ")) {
      index += 1;
      continue;
    }
    const oldPath = normalizeDiffPath(line.slice(4));
    index += 1;
    if (index >= lines.length || !lines[index].startsWith("+++ ")) {
      break;
    }
    const newPath = normalizeDiffPath(lines[index].slice(4));
    const file: PatchFile = { oldPath, newPath, hunks: [] };
    files.push(file);
    index += 1;

    while (index < lines.length && !lines[index].startsWith("--- ")) {
      if (lines[index].startsWith("@@")) {
        const header = lines[index];
        index += 1;
        const hunkLines: string[] = [];
        while (index < lines.length && !lines[index].startsWith("@@") && !lines[index].startsWith("--- ")) {
          hunkLines.push(lines[index]);
          index += 1;
        }
        const hunk: PatchHunk = { header, lines: hunkLines };
        file.hunks.push(hunk);
        continue;
      }
      index += 1;
    }
  }

  return { files };
}

export function validateUnifiedDiff(diff: string, scopeFence?: ScopeFence):
  | { ok: true; patch: Patch }
  | { ok: false; errors: DiffValidationError[] } {
  if (!diff.trim()) {
    return { ok: false, errors: [{ message: "Diff is empty" }] };
  }

  const patch = parseUnifiedDiff(diff);
  const errors: DiffValidationError[] = [];

  if (patch.files.length == 0) {
    errors.push({ message: "No file headers found in diff" });
  }

  if (scopeFence) {
    for (const file of patch.files) {
      const targetPath = file.newPath === "/dev/null" ? file.oldPath : file.newPath;
      if (targetPath && !isPathAllowed(targetPath, scopeFence)) {
        errors.push({ message: "File path out of scope", file: targetPath });
      }
    }
  }

  if (errors.length > 0) {
    return { ok: false, errors };
  }

  return { ok: true, patch };
}
