export type QueueJob<T> = {
  id: string;
  run: () => Promise<T>;
  priority?: number;
};

export class RunQueue {
  private readonly concurrency: number;
  private active = 0;
  private readonly queue: Array<QueueJob<unknown>> = [];

  constructor(concurrency = 1) {
    this.concurrency = Math.max(1, concurrency);
  }

  enqueue<T>(job: QueueJob<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      const wrapped: QueueJob<T> = {
        ...job,
        run: async () => {
          try {
            const result = await job.run();
            resolve(result);
            return result;
          } catch (error) {
            reject(error);
            throw error;
          }
        },
      };

      this.queue.push(wrapped);
      this.queue.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
      this.pump();
    });
  }

  private pump(): void {
    if (this.active >= this.concurrency) {
      return;
    }

    const next = this.queue.shift();
    if (!next) {
      return;
    }

    this.active += 1;
    void next.run().finally(() => {
      this.active -= 1;
      this.pump();
    });
  }
}
