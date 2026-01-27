import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export interface PatchApplyResult {
  ok: boolean;
  stdout: string;
  stderr: string;
}

async function runGitApply(root: string, diff: string, checkOnly: boolean): Promise<PatchApplyResult> {
  const tempFile = path.join(os.tmpdir(), `aict_patch_${Date.now()}.diff`);
  await fs.writeFile(tempFile, diff, "utf8");

  const args = ["apply", "--whitespace=nowarn"];
  if (checkOnly) {
    args.push("--check");
  }
  args.push(tempFile);

  return new Promise((resolve) => {
    execFile("git", args, { cwd: root }, (error, stdout, stderr) => {
      void fs.unlink(tempFile).catch(() => undefined);
      if (error) {
        resolve({ ok: false, stdout, stderr: stderr || String(error) });
        return;
      }
      resolve({ ok: true, stdout, stderr });
    });
  });
}

export function applyPatchDryRun(root: string, diff: string): Promise<PatchApplyResult> {
  return runGitApply(root, diff, true);
}

export function applyPatch(root: string, diff: string): Promise<PatchApplyResult> {
  return runGitApply(root, diff, false);
}
