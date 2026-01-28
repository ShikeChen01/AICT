import { validateDiffOutput, validatePlanOutput } from "src/extension/cloud/outputValidators";
import type { ProviderAdapter, ProviderResponse, PlanRequest, PatchRequest, ReviewRequest } from "src/extension/cloud/providerAdapter";
import type { Plan, UnifiedDiff } from "src/shared/types";

// Claude adapter: calls Anthropic Messages API and validates plan/diff outputs.
const DEFAULT_MODEL = "claude-3-5-sonnet-20241022";
const DEFAULT_MAX_TOKENS = 1024;
const ANTHROPIC_VERSION = "2023-06-01";

type ClaudeMessageResponse = {
  id: string;
  model: string;
  content: Array<{ type: "text"; text: string }>;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
  };
};

type FetchResponse = {
  ok: boolean;
  status: number;
  text: () => Promise<string>;
  json: () => Promise<ClaudeMessageResponse>;
};

type FetchFn = (input: string, init: Record<string, unknown>) => Promise<FetchResponse>;

const fetchFn = globalThis.fetch as unknown as FetchFn;

const readText = (payload: ClaudeMessageResponse): string =>
  payload.content.map((item) => item.text).join("");

const toUsage = (payload: ClaudeMessageResponse): ProviderResponse<string>["usage"] => ({
  inputTokens: payload.usage?.input_tokens,
  outputTokens: payload.usage?.output_tokens,
});

const extractText = async (response: FetchResponse): Promise<ClaudeMessageResponse> => {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Claude API error ${response.status}: ${body}`);
  }
  return (await response.json()) as ClaudeMessageResponse;
};

const createClaudeRequest = async (
  prompt: string,
  model: string,
  maxTokens: number,
  temperature: number,
  signal?: AbortSignal,
): Promise<ClaudeMessageResponse> => {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error("ANTHROPIC_API_KEY is not set.");
  }

  const response = await fetchFn("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": ANTHROPIC_VERSION,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      temperature,
      messages: [{ role: "user", content: prompt }],
    }),
    signal,
  });

  return extractText(response);
};

const buildPlanPrompt = (prompt: string): string => `${prompt}\n\nReturn ONLY valid JSON for the plan.`;
const buildPatchPrompt = (prompt: string): string =>
  `${prompt}\n\nReturn ONLY a unified diff (no code fences).`;
const buildReviewPrompt = (prompt: string): string => `${prompt}\n\nReturn review notes.`;

export class ClaudeAdapter implements ProviderAdapter {
  readonly name = "claude" as const;

  async plan(request: PlanRequest): Promise<ProviderResponse<Plan>> {
    const response = await createClaudeRequest(
      buildPlanPrompt(request.prompt),
      request.model ?? DEFAULT_MODEL,
      request.maxTokens ?? DEFAULT_MAX_TOKENS,
      request.temperature ?? 0.2,
      request.signal,
    );

    const raw = readText(response);
    const plan = validatePlanOutput(raw);

    return {
      output: plan,
      raw,
      model: response.model,
      usage: toUsage(response),
    };
  }

  async patch(request: PatchRequest): Promise<ProviderResponse<UnifiedDiff>> {
    const response = await createClaudeRequest(
      buildPatchPrompt(request.prompt),
      request.model ?? DEFAULT_MODEL,
      request.maxTokens ?? DEFAULT_MAX_TOKENS,
      request.temperature ?? 0.2,
      request.signal,
    );

    const raw = readText(response);
    const diff = validateDiffOutput(raw);

    return {
      output: diff,
      raw,
      model: response.model,
      usage: toUsage(response),
    };
  }

  async review(request: ReviewRequest): Promise<ProviderResponse<string>> {
    const response = await createClaudeRequest(
      buildReviewPrompt(request.prompt),
      request.model ?? DEFAULT_MODEL,
      request.maxTokens ?? DEFAULT_MAX_TOKENS,
      request.temperature ?? 0.2,
      request.signal,
    );

    const raw = readText(response);

    return {
      output: raw,
      raw,
      model: response.model,
      usage: toUsage(response),
    };
  }
}
