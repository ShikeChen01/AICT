import type { ProviderAdapter, ProviderRequest, ProviderResponse } from "./providerAdapter";

export interface OpenAIAdapterOptions {
  apiKey: string;
  endpoint: string;
  model: string;
}

export class OpenAIAdapter implements ProviderAdapter {
  readonly name = "openai" as const;
  private readonly apiKey: string;
  private readonly endpoint: string;
  private readonly model: string;

  constructor(options: OpenAIAdapterOptions) {
    this.apiKey = options.apiKey;
    this.endpoint = options.endpoint;
    this.model = options.model;
  }

  plan(request: ProviderRequest): Promise<ProviderResponse> {
    return this.callProvider("plan", request);
  }

  patch(request: ProviderRequest): Promise<ProviderResponse> {
    return this.callProvider("patch", request);
  }

  review(request: ProviderRequest): Promise<ProviderResponse> {
    return this.callProvider("review", request);
  }

  explainFailure(request: ProviderRequest): Promise<ProviderResponse> {
    return this.callProvider("explainFailure", request);
  }

  private async callProvider(type: string, request: ProviderRequest): Promise<ProviderResponse> {
    const payload = {
      model: this.model,
      input: [{ role: "user", content: request.input }],
      metadata: { type, scopeId: request.scopeId },
      stream: request.stream ?? false,
    };

    const response = await fetch(this.endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`OpenAI error ${response.status}: ${body}`);
    }

    if (request.stream && response.body) {
      const output = await readSseStream(response);
      return { output, raw: null };
    }

    const raw = await response.json();
    const output = extractText(raw);
    return { output, raw };
  }
}

async function readSseStream(response: Response): Promise<string> {
  const reader = response.body?.getReader();
  if (!reader) {
    return "";
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let output = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("
");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) {
        continue;
      }
      const data = trimmed.slice(5).trim();
      if (data === "[DONE]") {
        continue;
      }
      output += data;
    }
  }

  return output;
}

function extractText(raw: unknown): string {
  if (!raw || typeof raw !== "object") {
    return "";
  }
  const record = raw as { output_text?: string };
  if (typeof record.output_text === "string") {
    return record.output_text;
  }
  return JSON.stringify(raw);
}
