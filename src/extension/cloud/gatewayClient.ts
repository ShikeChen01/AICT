import type { ProviderAdapter, ProviderName, ProviderRequest, ProviderResponse } from "./providerAdapter";
import { RateLimiter } from "./rateLimiter";

export interface GatewayOptions {
  adapters: Record<ProviderName, ProviderAdapter>;
  defaultProvider: ProviderName;
  retries?: number;
  rateLimiter?: RateLimiter;
}

export class CloudGateway {
  private readonly adapters: Record<ProviderName, ProviderAdapter>;
  private readonly defaultProvider: ProviderName;
  private readonly retries: number;
  private readonly rateLimiter: RateLimiter;

  constructor(options: GatewayOptions) {
    this.adapters = options.adapters;
    this.defaultProvider = options.defaultProvider;
    this.retries = options.retries ?? 1;
    this.rateLimiter = options.rateLimiter ?? new RateLimiter();
  }

  plan(request: ProviderRequest, providerName?: ProviderName): Promise<ProviderResponse> {
    return this.callAdapter("plan", request, providerName);
  }

  patch(request: ProviderRequest, providerName?: ProviderName): Promise<ProviderResponse> {
    return this.callAdapter("patch", request, providerName);
  }

  review(request: ProviderRequest, providerName?: ProviderName): Promise<ProviderResponse> {
    return this.callAdapter("review", request, providerName);
  }

  explainFailure(request: ProviderRequest, providerName?: ProviderName): Promise<ProviderResponse> {
    return this.callAdapter("explainFailure", request, providerName);
  }

  private async callAdapter(
    method: "plan" | "patch" | "review" | "explainFailure",
    request: ProviderRequest,
    providerName?: ProviderName,
  ): Promise<ProviderResponse> {
    const provider = providerName ?? this.defaultProvider;
    const adapter = this.adapters[provider];
    if (!adapter) {
      throw new Error(`No adapter configured for ${provider}`);
    }

    const execute = () => adapter[method](request);

    let attempt = 0;
    while (true) {
      try {
        return await this.rateLimiter.schedule(execute);
      } catch (error) {
        attempt += 1;
        if (attempt > this.retries) {
          throw error;
        }
      }
    }
  }
}
