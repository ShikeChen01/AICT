import { UnifiedDiffSchema } from "src/shared/schemas/diffSchema";
import type { UnifiedDiff } from "src/shared/types/diff";
import type { ScopeFence } from "src/extension/policy/scopeFence";

export type DiffValidationError = {
  message: string;
  file?: string;
};

export type DiffValidationResult = {
  ok: boolean;
  errors: DiffValidationError[];
};

export const validateUnifiedDiff = (
  diff: UnifiedDiff,
  options?: { scopeFence?: ScopeFence },
): DiffValidationResult => {
  const validation = UnifiedDiffSchema.safeParse(diff);
  if (!validation.success) {
    return {
      ok: false,
      errors: [{ message: validation.error.message }],
    };
  }

  const errors: DiffValidationError[] = [];
  if (options?.scopeFence) {
    for (const file of diff.files) {
      const path = file.new_path ?? file.old_path;
      if (!options.scopeFence.isPathAllowed(path)) {
        errors.push({ message: "Out of scope diff file", file: path });
      }
    }
  }

  return { ok: errors.length === 0, errors };
};
