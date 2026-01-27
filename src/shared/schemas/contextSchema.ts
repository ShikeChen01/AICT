import { z } from "zod";

export const ContextFileSchema = z.object({
  path: z.string(),
  content: z.string(),
});

export const ContextLogSchema = z.object({
  source: z.string(),
  text: z.string(),
});

export const ContextBundleSchema = z.object({
  scopeId: z.string().optional(),
  files: z.array(ContextFileSchema),
  logs: z.array(ContextLogSchema),
  summaries: z.array(z.string()),
});
