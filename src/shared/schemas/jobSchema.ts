import { z } from "zod";

export const JobStatusSchema = z.enum(["queued", "running", "succeeded", "failed", "cancelled"]);
export const JobTypeSchema = z.enum(["plan", "patch", "test", "review", "index"]);

export const JobSchema = z.object({
  id: z.string(),
  type: JobTypeSchema,
  status: JobStatusSchema,
  createdAt: z.string(),
  updatedAt: z.string().optional(),
  message: z.string().optional(),
});
