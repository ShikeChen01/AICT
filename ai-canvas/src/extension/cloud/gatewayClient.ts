import type { ContextBundle, Plan, UnifiedDiff } from "src/shared/types";
import { ClaudeAdapter } from "src/extension/cloud/claudeAdapter";
import type { ProviderAdapter, PlanRequest, PatchRequest, ReviewRequest } from "src/extension/cloud/providerAdapter";
import { RateLimiter } from "src/extension/cloud/rateLimiter";

// Cloud gateway: routes plan/patch/review calls through a single adapter with rate limiting.
export type GatewayOptions = {
  adapter?: ProviderAdapter;
  rateLimiter?: RateLimiter;
};

export type PlanInput = {
  prompt: string;
  scopeId: string;
  context?: ContextBundle;
  signal?: AbortSignal;
};

export type PatchInput = {
  prompt: string;
  scopeId: string;
  context?: ContextBundle;
  signal?: AbortSignal;
};

export type ReviewInput = {
  prompt: string;
  diff: UnifiedDiff;
  signal?: AbortSignal;
};

const formatContext = (context?: ContextBundle): string => {
  if (!context || context.files.length === 0) {
    return "";
  }

  const header = "Context files (trimmed):";
  const blocks = context.files.map(
    (file) => `\n--- ${file.path} ---\n${file.content}`,
  );

  return `${header}${blocks.join("\n")}`;
};

const buildPlanRequest = (input: PlanInput): PlanRequest => ({
  prompt: `${input.prompt}\n\n${formatContext(input.context)}`.trim(),
  scopeId: input.scopeId,
  signal: input.signal,
});

const buildPatchRequest = (input: PatchInput): PatchRequest => ({
  prompt: `${input.prompt}\n\n${formatContext(input.context)}`.trim(),
  scopeId: input.scopeId,
  signal: input.signal,
});

const buildReviewRequest = (input: ReviewInput): ReviewRequest => ({
  prompt: input.prompt,
  diff: input.diff,
  signal: input.signal,
});

export class CloudGateway {
  private readonly adapter: ProviderAdapter;
  private readonly limiter: RateLimiter;

  constructor(options?: GatewayOptions) {
    this.adapter = options?.adapter ?? new ClaudeAdapter();
    this.limiter = options?.rateLimiter ?? new RateLimiter(2);
  }

  async plan(input: PlanInput): Promise<Plan> {
    return this.limiter.schedule(async () => {
      const response = await this.adapter.plan(buildPlanRequest(input));
      return response.output;
    });
  }

  async patch(input: PatchInput): Promise<UnifiedDiff> {
    return this.limiter.schedule(async () => {
      const response = await this.adapter.patch(buildPatchRequest(input));
      return response.output;
    });
  }

  async review(input: ReviewInput): Promise<string> {
    return this.limiter.schedule(async () => {
      const response = await this.adapter.review(buildReviewRequest(input));
      return response.output;
    });
  }
}
