import { z } from "zod";

export const WorkItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().optional(),
  files: z.array(z.string()).optional(),
});

export const StageSchema = z.object({
  id: z.string(),
  title: z.string(),
  items: z.array(WorkItemSchema),
});

export const PlanSchema = z.object({
  id: z.string(),
  scopeId: z.string().optional(),
  stages: z.array(StageSchema),
});
