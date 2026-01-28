import type { PlanStage } from "src/shared/types";

export type BatchPlan = {
  stages: PlanStage[];
};

export const planBatches = (stages: PlanStage[]): BatchPlan => ({
  stages,
});
