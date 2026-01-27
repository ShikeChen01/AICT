export class RequestTracker {
  private readonly pending = new Map<
    string,
    {
      resolve: (value: unknown) => void;
      reject: (reason?: unknown) => void;
      timeout: ReturnType<typeof setTimeout>;
    }
  >();

  constructor(private readonly timeoutMs = 30_000) {}

  create<T>(id: string): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("Request timed out"));
      }, this.timeoutMs);
      this.pending.set(id, { resolve, reject, timeout });
    });
  }

  resolve(id: string, value: unknown): void {
    const entry = this.pending.get(id);
    if (!entry) {
      return;
    }
    clearTimeout(entry.timeout);
    entry.resolve(value);
    this.pending.delete(id);
  }

  reject(id: string, reason: unknown): void {
    const entry = this.pending.get(id);
    if (!entry) {
      return;
    }
    clearTimeout(entry.timeout);
    entry.reject(reason);
    this.pending.delete(id);
  }

  clear(): void {
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timeout);
      entry.reject(new Error("Request tracker disposed"));
    }
    this.pending.clear();
  }
}
