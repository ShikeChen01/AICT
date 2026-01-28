import type { ProviderAdapter, PlanRequest, PatchRequest, ReviewRequest, ProviderResponse } from "src/extension/cloud/providerAdapter";
import type { Plan, UnifiedDiff } from "src/shared/types";

export class GeminiAdapter implements ProviderAdapter {
  readonly name = "gemini" as const;

  async plan(_request: PlanRequest): Promise<ProviderResponse<Plan>> {
    throw new Error("Gemini adapter is not configured. Use Claude for now.");
  }

  async patch(_request: PatchRequest): Promise<ProviderResponse<UnifiedDiff>> {
    throw new Error("Gemini adapter is not configured. Use Claude for now.");
  }

  async review(_request: ReviewRequest): Promise<ProviderResponse<string>> {
    throw new Error("Gemini adapter is not configured. Use Claude for now.");
  }
}
