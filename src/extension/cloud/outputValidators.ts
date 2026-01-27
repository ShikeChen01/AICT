import { z } from "zod";
import { PlanSchema } from "../../shared/schemas/planSchema";
import { UnifiedDiffSchema } from "../../shared/schemas/diffSchema";

export const ReviewSchema = z.object({
  summary: z.string(),
  risks: z.array(z.string()).default([]),
  suggestions: z.array(z.string()).default([]),
});

export type ValidationResult<T> = { ok: true; data: T } | { ok: false; error: string };

export function validatePlan(payload: unknown): ValidationResult<z.infer<typeof PlanSchema>> {
  const result = PlanSchema.safeParse(payload);
  if (!result.success) {
    return { ok: false, error: result.error.message };
  }
  return { ok: true, data: result.data };
}

export function validateReview(payload: unknown): ValidationResult<z.infer<typeof ReviewSchema>> {
  const result = ReviewSchema.safeParse(payload);
  if (!result.success) {
    return { ok: false, error: result.error.message };
  }
  return { ok: true, data: result.data };
}

export function validateDiff(payload: unknown): ValidationResult<z.infer<typeof UnifiedDiffSchema>> {
  const result = UnifiedDiffSchema.safeParse(payload);
  if (!result.success) {
    return { ok: false, error: result.error.message };
  }
  return { ok: true, data: result.data };
}
