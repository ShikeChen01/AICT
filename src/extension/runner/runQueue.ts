export interface QueueJob<T> {
  id: string;
  priority?: number;
  run: () => Promise<T>;
}

export class RunQueue {
  private readonly concurrency: number;
  private running = 0;
  private queue: Array<{
    job: QueueJob<unknown>;
    resolve: (value: unknown) => void;
    reject: (reason?: unknown) => void;
  }> = [];

  constructor(options: { concurrency?: number } = {}) {
    this.concurrency = options.concurrency ?? 1;
  }

  enqueue<T>(job: QueueJob<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      this.queue.push({ job: job as QueueJob<unknown>, resolve, reject });
      this.queue.sort((a, b) => (b.job.priority ?? 0) - (a.job.priority ?? 0));
      this.pump();
    });
  }

  private pump(): void {
    while (this.running < this.concurrency && this.queue.length > 0) {
      const next = this.queue.shift();
      if (!next) {
        return;
      }
      this.running += 1;
      next.job
        .run()
        .then((result) => {
          next.resolve(result);
        })
        .catch((error) => {
          next.reject(error);
        })
        .finally(() => {
          this.running -= 1;
          this.pump();
        });
    }
  }
}
