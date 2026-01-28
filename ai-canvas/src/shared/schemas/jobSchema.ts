import { z } from "zod";
import type { Job } from "src/shared/types/jobs";

const JobTypeSchema = z.enum(["work", "tests", "patch", "index", "export", "review"]);

const JobStatusSchema = z.enum(["queued", "running", "succeeded", "failed", "canceled"]);

const JobSchema: z.ZodType<Job> = z.object({
  id: z.string().min(1),
  type: JobTypeSchema,
  status: JobStatusSchema,
  created_at: z.string().min(1),
  started_at: z.string().min(1).optional(),
  finished_at: z.string().min(1).optional(),
  progress: z.number().min(0).max(1).optional(),
  message: z.string().optional(),
  error: z.string().optional(),
});

export { JobSchema, JobStatusSchema };
