import parseDiff from "parse-diff";
import { PlanSchema } from "src/shared/schemas/planSchema";
import type { Plan, UnifiedDiff, DiffFile, DiffHunk } from "src/shared/types";

const extractJson = (text: string): unknown => {
  try {
    return JSON.parse(text);
  } catch {
    const fenced = text.match(/```json\s*([\s\S]*?)```/i);
    if (fenced?.[1]) {
      return JSON.parse(fenced[1]);
    }

    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    if (start !== -1 && end !== -1 && end > start) {
      const slice = text.slice(start, end + 1);
      return JSON.parse(slice);
    }
  }
  throw new Error("Unable to parse JSON from model output.");
};

const toUnifiedDiff = (text: string): UnifiedDiff => {
  const parsed = parseDiff(text);
  const files: DiffFile[] = parsed.map((file) => {
    const hunks: DiffHunk[] = file.chunks.map((chunk) => ({
      old_start: chunk.oldStart,
      old_lines: chunk.oldLines,
      new_start: chunk.newStart,
      new_lines: chunk.newLines,
      header: chunk.content,
      lines: chunk.changes.map((change) => change.content),
    }));

    return {
      old_path: file.from ?? "",
      new_path: file.to ?? "",
      hunks,
      is_new: file.from === "/dev/null",
      is_deleted: file.to === "/dev/null",
    };
  });

  return { text, files };
};

export const validatePlanOutput = (raw: string): Plan => {
  const json = extractJson(raw);
  const parsed = PlanSchema.safeParse(json);
  if (!parsed.success) {
    throw new Error(`Plan output failed schema validation: ${parsed.error.message}`);
  }
  return parsed.data;
};

export const validateDiffOutput = (raw: string): UnifiedDiff => {
  if (!raw.includes("@@")) {
    throw new Error("Unified diff output missing hunk headers.");
  }

  return toUnifiedDiff(raw.trim());
};
