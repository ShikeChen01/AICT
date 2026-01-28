import type { Guardrails } from "src/shared/types/rpc";
import type { UnifiedDiff } from "src/shared/types/diff";
import { CommandAllowlist } from "src/extension/policy/commandAllowlist";
import { DependencyGate } from "src/extension/policy/dependencyGate";
import { NetworkPolicy } from "src/extension/policy/networkPolicy";
import { ScopeFence } from "src/extension/policy/scopeFence";

// Policy engine: aggregate guardrails for commands, scope fences, dependency edits, and network usage.
export type PolicyDecision = {
  allow: boolean;
  reasons: string[];
};

export type PolicyContext = {
  kind: "startWork" | "runTests" | "applyPatch" | "repoIndex" | "exportBundle";
  command?: string;
  diff?: UnifiedDiff;
  guardrails?: Guardrails;
  scopeFence?: ScopeFence;
  allowNetwork?: boolean;
  scopeId?: string;
};

export class PolicyEngine {
  private readonly allowlist: CommandAllowlist;
  private readonly dependencyGate: DependencyGate;
  private readonly networkPolicy: NetworkPolicy;

  constructor(options?: {
    allowlist?: CommandAllowlist;
    dependencyGate?: DependencyGate;
    networkPolicy?: NetworkPolicy;
  }) {
    this.allowlist = options?.allowlist ?? new CommandAllowlist();
    this.dependencyGate = options?.dependencyGate ?? new DependencyGate();
    this.networkPolicy = options?.networkPolicy ?? new NetworkPolicy(true);
  }

  evaluate(context: PolicyContext): PolicyDecision {
    const reasons: string[] = [];

    if (context.command && !this.allowlist.isCommandAllowed(context.command)) {
      reasons.push(`Command not allowlisted: ${context.command}`);
    }

    if (context.diff && context.guardrails?.block_deps) {
      const dependencyChanges = this.dependencyGate.detectDependencyChanges(context.diff);
      if (dependencyChanges.length > 0) {
        reasons.push("Dependency changes require explicit approval.");
      }
    }

    if (context.diff && context.guardrails?.enforce_scope && context.scopeFence) {
      for (const file of context.diff.files) {
        const candidate = file.new_path ?? file.old_path;
        if (!context.scopeFence.isPathAllowed(candidate)) {
          reasons.push(`Out-of-scope path: ${candidate}`);
        }
      }
    }

    if (context.guardrails?.block_network && context.allowNetwork) {
      const decision = this.networkPolicy.evaluate(true);
      if (!decision.allow) {
        reasons.push(decision.reason ?? "Network access blocked.");
      }
    }

    return {
      allow: reasons.length === 0,
      reasons,
    };
  }
}
