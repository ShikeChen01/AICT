import type { UnifiedDiff } from "src/shared/types/diff";
import { validateUnifiedDiff } from "src/extension/patch/diffValidator";
import { applyPatch, applyPatchDryRun } from "src/extension/patch/patchApplier";
import { runFormatters } from "src/extension/patch/formatRunner";
import type { PolicyEngine } from "src/extension/policy/policyEngine";
import type { ScopeFence } from "src/extension/policy/scopeFence";
import type { CommandRunner } from "src/extension/runner/commandRunner";

// Patch engine: validate, dry-run, optionally format, then apply a unified diff.
export type PatchApplyResult = {
  ok: boolean;
  errors?: string[];
};

export type PatchEngineOptions = {
  runner: CommandRunner;
  policy: PolicyEngine;
  scopeFence?: ScopeFence;
  formatCommands?: string[];
};

export type PatchApplyInput = {
  diff: UnifiedDiff;
  root: string;
  runFormatters: boolean;
};

export class PatchEngine {
  private readonly runner: CommandRunner;
  private readonly policy: PolicyEngine;
  private readonly scopeFence?: ScopeFence;
  private readonly formatCommands: string[];

  constructor(options: PatchEngineOptions) {
    this.runner = options.runner;
    this.policy = options.policy;
    this.scopeFence = options.scopeFence;
    this.formatCommands = options.formatCommands ?? [];
  }

  async applyPatch(input: PatchApplyInput): Promise<PatchApplyResult> {
    const validation = validateUnifiedDiff(input.diff, { scopeFence: this.scopeFence });
    if (!validation.ok) {
      return { ok: false, errors: validation.errors.map((error) => error.message) };
    }

    const dryRun = applyPatchDryRun(input.diff, input.root);
    if (!dryRun.ok) {
      return { ok: false, errors: dryRun.errors };
    }

    if (input.runFormatters && this.formatCommands.length > 0) {
      await runFormatters(this.formatCommands, input.root, this.runner, this.policy);
    }

    const applied = applyPatch(input.diff, input.root);
    if (!applied.ok) {
      return { ok: false, errors: applied.errors };
    }

    return { ok: true };
  }
}
