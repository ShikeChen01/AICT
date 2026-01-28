export type RequestTrackerOptions = {
  timeoutMs?: number;
};

export type PendingRequest = {
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
  timer?: number;
};

export class RequestTracker {
  private readonly pending = new Map<string, PendingRequest>();
  private readonly timeoutMs: number;

  constructor(options?: RequestTrackerOptions) {
    this.timeoutMs = options?.timeoutMs ?? 60_000;
  }

  create<T>(id: string): Promise<T> {
    return new Promise((resolve, reject) => {
      const entry: PendingRequest = { resolve: resolve as (value: unknown) => void, reject };
      if (this.timeoutMs > 0) {
        entry.timer = window.setTimeout(() => {
          this.pending.delete(id);
          reject(new Error("RPC request timed out"));
        }, this.timeoutMs);
      }
      this.pending.set(id, entry);
    });
  }

  resolve<T>(id: string, payload: T): void {
    const entry = this.pending.get(id);
    if (!entry) {
      return;
    }
    if (entry.timer) {
      window.clearTimeout(entry.timer);
    }
    entry.resolve(payload);
    this.pending.delete(id);
  }

  reject(id: string, error: unknown): void {
    const entry = this.pending.get(id);
    if (!entry) {
      return;
    }
    if (entry.timer) {
      window.clearTimeout(entry.timer);
    }
    entry.reject(error);
    this.pending.delete(id);
  }
}
