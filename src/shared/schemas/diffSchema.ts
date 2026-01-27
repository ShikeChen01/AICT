import { z } from "zod";

export const DiffHunkSchema = z.object({
  header: z.string(),
  lines: z.array(z.string()),
});

export const DiffFileSchema = z.object({
  oldPath: z.string(),
  newPath: z.string(),
  hunks: z.array(DiffHunkSchema),
});

export const UnifiedDiffSchema = z.object({
  files: z.array(DiffFileSchema),
});
