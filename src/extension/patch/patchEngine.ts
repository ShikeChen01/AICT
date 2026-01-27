import type { CommandAllowlist } from "../policy/commandAllowlist";
import type { PolicyEngine } from "../policy/policyEngine";
import type { ScopeFence } from "../policy/scopeFence";
import { validateUnifiedDiff } from "./diffValidator";
import { applyPatch, applyPatchDryRun } from "./patchApplier";
import type { FormatRunResult } from "./formatRunner";
import { runFormatters } from "./formatRunner";

export interface PatchApplyResult {
  ok: boolean;
  errors?: string[];
  dryRun: boolean;
  applied: boolean;
  formatResults?: FormatRunResult[];
}

export interface PatchEngineOptions {
  root: string;
  policyEngine: PolicyEngine;
  scopeFence: ScopeFence;
  allowlist: CommandAllowlist;
}

export class PatchEngine {
  private readonly root: string;
  private readonly policyEngine: PolicyEngine;
  private readonly scopeFence: ScopeFence;
  private readonly allowlist: CommandAllowlist;

  constructor(options: PatchEngineOptions) {
    this.root = options.root;
    this.policyEngine = options.policyEngine;
    this.scopeFence = options.scopeFence;
    this.allowlist = options.allowlist;
  }

  async applyPatch(
    diff: string,
    options: { dryRun?: boolean; format?: boolean; formatCommands?: string[] } = {},
  ): Promise<PatchApplyResult> {
    const validation = validateUnifiedDiff(diff, this.scopeFence);
    if (!validation.ok) {
      return { ok: false, dryRun: true, applied: false, errors: validation.errors.map((err) => err.message) };
    }

    const filePaths = validation.patch.files.map((file) =>
      file.newPath === "/dev/null" ? file.oldPath : file.newPath,
    );
    const decision = this.policyEngine.evaluate({ diffText: diff, paths: filePaths });
    if (!decision.allowed) {
      return { ok: false, dryRun: true, applied: false, errors: decision.reasons };
    }

    const dryRunResult = await applyPatchDryRun(this.root, diff);
    if (!dryRunResult.ok) {
      return { ok: false, dryRun: true, applied: false, errors: [dryRunResult.stderr || "Dry run failed"] };
    }

    let formatResults: FormatRunResult[] | undefined;
    if (options.format && options.formatCommands && options.formatCommands.length > 0) {
      formatResults = await runFormatters(options.formatCommands, { cwd: this.root, allowlist: this.allowlist });
    }

    if (options.dryRun) {
      return { ok: true, dryRun: true, applied: false, formatResults };
    }

    const applyResult = await applyPatch(this.root, diff);
    if (!applyResult.ok) {
      return { ok: false, dryRun: false, applied: false, errors: [applyResult.stderr || "Patch apply failed"] };
    }

    return { ok: true, dryRun: false, applied: true, formatResults };
  }
}
