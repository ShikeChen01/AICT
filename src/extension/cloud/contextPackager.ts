import type { ContextBundle, ContextFile, ContextLog } from "../../shared/types";

export interface ContextBundleOptions {
  scopeId?: string;
  files: ContextFile[];
  logs?: ContextLog[];
  summaries?: string[];
  byteCap?: number;
}

function estimateBytes(text: string): number {
  return Buffer.byteLength(text, "utf8");
}

function truncateText(text: string, maxBytes: number): string {
  const buffer = Buffer.from(text, "utf8");
  if (buffer.length <= maxBytes) {
    return text;
  }
  return buffer.subarray(0, maxBytes).toString("utf8");
}

export function buildContextBundle(options: ContextBundleOptions): ContextBundle {
  const byteCap = options.byteCap ?? 500_000;
  const summaries = options.summaries ?? [];
  const logs = options.logs ?? [];
  const files = options.files ?? [];

  let total = 0;
  const trimmedFiles: ContextFile[] = [];
  const trimmedLogs: ContextLog[] = [];
  const trimmedSummaries: string[] = [];

  for (const summary of summaries) {
    const bytes = estimateBytes(summary);
    if (total + bytes > byteCap) {
      const remaining = Math.max(0, byteCap - total);
      if (remaining > 0) {
        trimmedSummaries.push(truncateText(summary, remaining));
        total = byteCap;
      }
      break;
    }
    trimmedSummaries.push(summary);
    total += bytes;
  }

  for (const log of logs) {
    const bytes = estimateBytes(log.text);
    if (total + bytes > byteCap) {
      const remaining = Math.max(0, byteCap - total);
      if (remaining > 0) {
        trimmedLogs.push({ source: log.source, text: truncateText(log.text, remaining) });
        total = byteCap;
      }
      break;
    }
    trimmedLogs.push(log);
    total += bytes;
  }

  for (const file of files) {
    const bytes = estimateBytes(file.content);
    if (total + bytes > byteCap) {
      const remaining = Math.max(0, byteCap - total);
      if (remaining > 0) {
        trimmedFiles.push({ path: file.path, content: truncateText(file.content, remaining) });
        total = byteCap;
      }
      break;
    }
    trimmedFiles.push(file);
    total += bytes;
  }

  return {
    scopeId: options.scopeId,
    files: trimmedFiles,
    logs: trimmedLogs,
    summaries: trimmedSummaries,
  };
}
