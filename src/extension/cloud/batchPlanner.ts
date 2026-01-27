export interface BatchPlan {
  planBatches: Batch[];
  patchBatches: Batch[];
}

export interface Batch {
  id: string;
  items: string[];
}

export function planBatches(
  scope: { items: string[] },
  options: { maxItemsPerBatch?: number } = {},
): BatchPlan {
  const maxItems = options.maxItemsPerBatch ?? 10;
  const planBatches: Batch[] = [];
  const patchBatches: Batch[] = [];

  let batchIndex = 0;
  for (let i = 0; i < scope.items.length; i += maxItems) {
    const items = scope.items.slice(i, i + maxItems);
    const id = `batch_${batchIndex}`;
    planBatches.push({ id: `${id}_plan`, items });
    patchBatches.push({ id: `${id}_patch`, items });
    batchIndex += 1;
  }

  return { planBatches, patchBatches };
}
