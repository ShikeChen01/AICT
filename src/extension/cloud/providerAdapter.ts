import type { ContextBundle } from "../../shared/types";

export type ProviderName = "openai" | "claude" | "gemini";

export interface ProviderRequest {
  scopeId?: string;
  context: ContextBundle;
  input: string;
  stream?: boolean;
}

export interface ProviderResponse {
  output: string;
  raw?: unknown;
}

export interface ProviderAdapter {
  name: ProviderName;
  plan(request: ProviderRequest): Promise<ProviderResponse>;
  patch(request: ProviderRequest): Promise<ProviderResponse>;
  review(request: ProviderRequest): Promise<ProviderResponse>;
  explainFailure(request: ProviderRequest): Promise<ProviderResponse>;
}
