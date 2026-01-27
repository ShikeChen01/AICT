import assert from "node:assert/strict";
import { test } from "node:test";
import { RunQueue } from "../../src/extension/runner/runQueue";

test("run queue honors priority among queued jobs", async () => {
  const queue = new RunQueue({ concurrency: 1 });
  const order: string[] = [];
  let releaseFirst: (() => void) | undefined;

  const gate = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });

  const job1 = queue.enqueue({
    id: "first",
    priority: 0,
    run: async () => {
      order.push("first");
      await gate;
    },
  });

  const job2 = queue.enqueue({
    id: "low",
    priority: 1,
    run: async () => {
      order.push("low");
    },
  });

  const job3 = queue.enqueue({
    id: "high",
    priority: 10,
    run: async () => {
      order.push("high");
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 10));
  releaseFirst?.();

  await Promise.all([job1, job2, job3]);
  assert.deepEqual(order, ["first", "high", "low"]);
});
