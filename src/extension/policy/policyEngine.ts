import type { CommandAllowlist } from "./commandAllowlist";
import { isCommandAllowed } from "./commandAllowlist";
import { detectDependencyChanges } from "./dependencyGate";
import type { NetworkPolicy } from "./networkPolicy";
import { evaluateNetworkPolicy } from "./networkPolicy";
import type { ScopeFence } from "./scopeFence";
import { isPathAllowed } from "./scopeFence";

export interface PolicyContext {
  command?: string;
  paths?: string[];
  diffText?: string;
  networkKind?: "test" | "tool";
}

export interface PolicyDecision {
  allowed: boolean;
  reasons: string[];
}

export class PolicyEngine {
  private readonly scopeFence?: ScopeFence;
  private readonly commandAllowlist?: CommandAllowlist;
  private readonly networkPolicy?: NetworkPolicy;

  constructor(options: {
    scopeFence?: ScopeFence;
    commandAllowlist?: CommandAllowlist;
    networkPolicy?: NetworkPolicy;
  }) {
    this.scopeFence = options.scopeFence;
    this.commandAllowlist = options.commandAllowlist;
    this.networkPolicy = options.networkPolicy;
  }

  evaluate(context: PolicyContext): PolicyDecision {
    const reasons: string[] = [];
    let allowed = true;

    if (context.paths && this.scopeFence) {
      const invalidPaths = context.paths.filter((entry) => !isPathAllowed(entry, this.scopeFence));
      if (invalidPaths.length > 0) {
        allowed = false;
        reasons.push(`Paths out of scope: ${invalidPaths.join(", ")}`);
      }
      if (this.scopeFence.maxFiles && context.paths.length > this.scopeFence.maxFiles) {
        allowed = false;
        reasons.push(`Max file limit exceeded (${this.scopeFence.maxFiles})`);
      }
    }

    if (context.command && this.commandAllowlist) {
      if (!isCommandAllowed(context.command, this.commandAllowlist)) {
        allowed = false;
        reasons.push(`Command not allowlisted: ${context.command}`);
      }
    }

    if (context.diffText) {
      const changes = detectDependencyChanges(context.diffText);
      if (changes.length > 0) {
        allowed = false;
        reasons.push("Dependency changes require approval");
      }
    }

    if (context.networkKind && this.networkPolicy) {
      const decision = evaluateNetworkPolicy(this.networkPolicy, context.networkKind);
      if (!decision.allowed) {
        allowed = false;
        if (decision.reason) {
          reasons.push(decision.reason);
        }
      }
    }

    return { allowed, reasons };
  }
}
