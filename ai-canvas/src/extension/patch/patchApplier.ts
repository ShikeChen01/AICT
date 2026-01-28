import * as fs from "node:fs";
import * as path from "node:path";
import { applyPatch as applyPatchToText, parsePatch } from "diff";
import type { UnifiedDiff } from "src/shared/types/diff";

export type PatchApplyResult = {
  ok: boolean;
  errors: string[];
};

const normalizePath = (raw: string): string => raw.replace(/^([ab])\//, "");

const resolveFile = (root: string, filename: string): string =>
  path.resolve(root, normalizePath(filename));

const applySinglePatch = (root: string, patchText: string, dryRun: boolean): string[] => {
  const errors: string[] = [];
  const patches = parsePatch(patchText);

  for (const patch of patches) {
    const oldName = patch.oldFileName ?? "";
    const newName = patch.newFileName ?? "";

    const isNew = oldName === "/dev/null";
    const isDeleted = newName === "/dev/null";

    const targetPath = resolveFile(root, isDeleted ? oldName : newName);
    const existing = fs.existsSync(targetPath) ? fs.readFileSync(targetPath, "utf8") : "";
    const patched = applyPatchToText(existing, patch);

    if (patched === false) {
      errors.push(`Failed to apply patch for ${targetPath}`);
      continue;
    }

    if (dryRun) {
      continue;
    }

    if (isDeleted) {
      if (fs.existsSync(targetPath)) {
        fs.unlinkSync(targetPath);
      }
      continue;
    }

    if (isNew) {
      fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    }

    fs.writeFileSync(targetPath, patched, "utf8");
  }

  return errors;
};

export const applyPatchDryRun = (diff: UnifiedDiff, root: string): PatchApplyResult => {
  const errors = applySinglePatch(root, diff.text, true);
  return { ok: errors.length === 0, errors };
};

export const applyPatch = (diff: UnifiedDiff, root: string): PatchApplyResult => {
  const errors = applySinglePatch(root, diff.text, false);
  return { ok: errors.length === 0, errors };
};
