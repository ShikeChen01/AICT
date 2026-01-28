import type { ProviderAdapter, PlanRequest, PatchRequest, ReviewRequest, ProviderResponse } from "src/extension/cloud/providerAdapter";
import type { Plan, UnifiedDiff } from "src/shared/types";

export class OpenAIAdapter implements ProviderAdapter {
  readonly name = "openai" as const;

  async plan(_request: PlanRequest): Promise<ProviderResponse<Plan>> {
    throw new Error("OpenAI adapter is not configured. Use Claude for now.");
  }

  async patch(_request: PatchRequest): Promise<ProviderResponse<UnifiedDiff>> {
    throw new Error("OpenAI adapter is not configured. Use Claude for now.");
  }

  async review(_request: ReviewRequest): Promise<ProviderResponse<string>> {
    throw new Error("OpenAI adapter is not configured. Use Claude for now.");
  }
}
