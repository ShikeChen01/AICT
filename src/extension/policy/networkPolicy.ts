export interface NetworkPolicy {
  allowDuringTests: boolean;
  allowDuringTools: boolean;
}

export interface NetworkPolicyDecision {
  allowed: boolean;
  reason?: string;
}

export function evaluateNetworkPolicy(policy: NetworkPolicy, kind: "test" | "tool"): NetworkPolicyDecision {
  if (kind === "test") {
    return policy.allowDuringTests
      ? { allowed: true }
      : { allowed: false, reason: "Network calls blocked during tests" };
  }

  return policy.allowDuringTools
    ? { allowed: true }
    : { allowed: false, reason: "Network calls blocked during tool execution" };
}
