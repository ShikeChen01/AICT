export class RateLimiter {
  private readonly concurrency: number;
  private readonly backoffMs: number;
  private readonly queue: Array<() => void> = [];
  private running = 0;
  private nextAvailable = 0;

  constructor(options: { concurrency?: number; backoffMs?: number } = {}) {
    this.concurrency = options.concurrency ?? 2;
    this.backoffMs = options.backoffMs ?? 1_000;
  }

  async schedule<T>(task: () => Promise<T>): Promise<T> {
    await this.waitForSlot();
    this.running += 1;
    try {
      const result = await task();
      return result;
    } catch (error) {
      this.registerFailure();
      throw error;
    } finally {
      this.running -= 1;
      this.release();
    }
  }

  private async waitForSlot(): Promise<void> {
    if (this.running < this.concurrency && Date.now() >= this.nextAvailable) {
      return;
    }
    await new Promise<void>((resolve) => {
      this.queue.push(resolve);
    });
  }

  private release(): void {
    if (this.queue.length === 0) {
      return;
    }
    const waitTime = Math.max(0, this.nextAvailable - Date.now());
    const next = this.queue.shift();
    if (!next) {
      return;
    }
    if (waitTime == 0 && this.running < this.concurrency) {
      next();
      return;
    }
    setTimeout(next, waitTime);
  }

  private registerFailure(): void {
    this.nextAvailable = Date.now() + this.backoffMs;
  }
}
