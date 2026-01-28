import { z } from "zod";
import type { ContextBundle } from "src/shared/types/context";

const ContextFileSchema = z.object({
  path: z.string().min(1),
  content: z.string(),
  byte_size: z.number().int().nonnegative(),
  mime_type: z.string().optional(),
});

const ContextLogSchema = z.object({
  source: z.string().min(1),
  content: z.string(),
  truncated: z.boolean().optional(),
});

const ContextBundleSchema: z.ZodType<ContextBundle> = z.object({
  id: z.string().min(1),
  scope_id: z.string().min(1),
  files: z.array(ContextFileSchema),
  logs: z.array(ContextLogSchema),
  created_at: z.string().min(1),
  byte_size: z.number().int().nonnegative(),
  token_estimate: z.number().int().nonnegative().optional(),
});

export { ContextBundleSchema };
