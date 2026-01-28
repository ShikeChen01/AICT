import type { ContextBundle, Plan, UnifiedDiff } from "src/shared/types";

export type ProviderName = "claude" | "openai" | "gemini";

export type ProviderUsage = {
  inputTokens?: number;
  outputTokens?: number;
};

export type ProviderResponse<T> = {
  output: T;
  raw: string;
  model: string;
  usage?: ProviderUsage;
};

export type ProviderRequestBase = {
  prompt: string;
  model?: string;
  maxTokens?: number;
  temperature?: number;
  context?: ContextBundle;
  signal?: AbortSignal;
};

export type PlanRequest = ProviderRequestBase & {
  scopeId: string;
};

export type PatchRequest = ProviderRequestBase & {
  scopeId: string;
  plan?: Plan;
};

export type ReviewRequest = ProviderRequestBase & {
  diff: UnifiedDiff;
};

export interface ProviderAdapter {
  readonly name: ProviderName;
  plan(request: PlanRequest): Promise<ProviderResponse<Plan>>;
  patch(request: PatchRequest): Promise<ProviderResponse<UnifiedDiff>>;
  review(request: ReviewRequest): Promise<ProviderResponse<string>>;
}
