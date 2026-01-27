import type { ProviderAdapter, ProviderRequest, ProviderResponse } from "./providerAdapter";

export interface ClaudeAdapterOptions {
  apiKey: string;
  endpoint: string;
  model: string;
}

export class ClaudeAdapter implements ProviderAdapter {
  readonly name = "claude" as const;
  private readonly apiKey: string;
  private readonly endpoint: string;
  private readonly model: string;

  constructor(options: ClaudeAdapterOptions) {
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
      messages: [{ role: "user", content: request.input }],
      metadata: { type, scopeId: request.scopeId },
      stream: request.stream ?? false,
    };

    const response = await fetch(this.endpoint, {
      method: "POST",
      headers: {
        "x-api-key": this.apiKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Claude error ${response.status}: ${body}`);
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
  const record = raw as { content?: Array<{ type?: string; text?: string }> };
  if (Array.isArray(record.content)) {
    return record.content.map((item) => item.text ?? "").join("");
  }
  return JSON.stringify(raw);
}
