export class RateLimiter {
  private readonly maxConcurrent: number;
  private active = 0;
  private readonly queue: Array<() => void> = [];

  constructor(maxConcurrent = 2) {
    this.maxConcurrent = Math.max(1, maxConcurrent);
  }

  async schedule<T>(task: () => Promise<T>): Promise<T> {
    await this.acquire();
    try {
      return await task();
    } finally {
      this.release();
    }
  }

  private acquire(): Promise<void> {
    if (this.active < this.maxConcurrent) {
      this.active += 1;
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      this.queue.push(() => {
        this.active += 1;
        resolve();
      });
    });
  }

  private release(): void {
    this.active = Math.max(0, this.active - 1);
    const next = this.queue.shift();
    if (next) {
      next();
    }
  }
}
