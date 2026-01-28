import { z } from "zod";
import type { UnifiedDiff } from "src/shared/types/diff";

const DiffHunkSchema = z.object({
  old_start: z.number().int().nonnegative(),
  old_lines: z.number().int().nonnegative(),
  new_start: z.number().int().nonnegative(),
  new_lines: z.number().int().nonnegative(),
  header: z.string().optional(),
  lines: z.array(z.string()),
});

const DiffFileSchema = z.object({
  old_path: z.string(),
  new_path: z.string(),
  hunks: z.array(DiffHunkSchema),
  is_new: z.boolean().optional(),
  is_deleted: z.boolean().optional(),
});

const UnifiedDiffSchema: z.ZodType<UnifiedDiff> = z.object({
  text: z.string(),
  files: z.array(DiffFileSchema),
});

export { UnifiedDiffSchema };
