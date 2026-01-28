export type NetworkPolicyDecision = {
  allow: boolean;
  reason?: string;
};

export class NetworkPolicy {
  private readonly allowNetwork: boolean;

  constructor(allowNetwork = true) {
    this.allowNetwork = allowNetwork;
  }

  evaluate(requested: boolean): NetworkPolicyDecision {
    if (!requested) {
      return { allow: true };
    }

    if (!this.allowNetwork) {
      return { allow: false, reason: "Network access is disabled by policy." };
    }

    return { allow: true };
  }
}
