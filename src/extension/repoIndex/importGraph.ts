import fs from "node:fs/promises";
import path from "node:path";

export interface ImportGraph {
  entries: Record<string, string[]>;
}

const TS_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx"]);

function extractTsImports(text: string): string[] {
  const imports: string[] = [];
  const regex = /(?:from\s+["']([^"']+)["'])|(?:require\(\s*["']([^"']+)["']\s*\))/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) != null) {
    imports.push(match[1] || match[2]);
  }
  return imports;
}

function extractPythonImports(text: string): string[] {
  const imports: string[] = [];
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("import ")) {
      imports.push(trimmed.replace(/^import\s+/, "").split(" ")[0]);
    } else if (trimmed.startsWith("from ")) {
      const parts = trimmed.split(" ");
      if (parts.length > 1) {
        imports.push(parts[1]);
      }
    }
  }
  return imports;
}

export async function buildImportGraph(files: string[]): Promise<ImportGraph> {
  const entries: Record<string, string[]> = {};

  for (const file of files) {
    const ext = path.extname(file);
    if (!TS_EXTENSIONS.has(ext) && ext !== ".py") {
      continue;
    }
    const text = await fs.readFile(file, "utf8");
    if (TS_EXTENSIONS.has(ext)) {
      entries[file] = extractTsImports(text);
    } else {
      entries[file] = extractPythonImports(text);
    }
  }

  return { entries };
}
