import { z } from "zod";
import type { Plan, PlanStage } from "src/shared/types/plan";

const WorkItemSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  description: z.string().optional(),
  type: z.enum(["code", "test", "refactor", "docs", "analysis"]),
  status: z.enum(["todo", "doing", "done"]).optional(),
  target_entity_id: z.string().min(1).optional(),
  files: z.array(z.string()).optional(),
});

const StageSchema: z.ZodType<PlanStage> = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  summary: z.string().optional(),
  depends_on: z.array(z.string()).optional(),
  work_items: z.array(WorkItemSchema),
  tests: z.array(z.string()).optional(),
});

const PlanSchema: z.ZodType<Plan> = z.object({
  id: z.string().min(1),
  scope_id: z.string().min(1),
  title: z.string().optional(),
  summary: z.string().optional(),
  stages: z.array(StageSchema),
  risks: z.array(z.string()).optional(),
  assumptions: z.array(z.string()).optional(),
});

export { PlanSchema, StageSchema };
