import fs from "node:fs/promises";
import path from "node:path";

export interface SymbolInfo {
  file: string;
  exports: string[];
}

const TS_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx"]);

function extractTsExports(text: string): string[] {
  const symbols: string[] = [];
  const regex = /export\s+(?:async\s+)?(?:function|class|const|interface|type|enum)\s+([A-Za-z0-9_]+)/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) != null) {
    symbols.push(match[1]);
  }
  return symbols;
}

function extractPythonExports(text: string): string[] {
  const symbols: string[] = [];
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("def ")) {
      const name = trimmed.replace(/^def\s+/, "").split("(")[0];
      symbols.push(name);
    } else if (trimmed.startsWith("class ")) {
      const name = trimmed.replace(/^class\s+/, "").split("(")[0].split(":")[0];
      symbols.push(name);
    }
  }
  return symbols;
}

export async function extractExportedSymbols(files: string[]): Promise<SymbolInfo[]> {
  const results: SymbolInfo[] = [];
  for (const file of files) {
    const ext = path.extname(file);
    if (!TS_EXTENSIONS.has(ext) && ext !== ".py") {
      continue;
    }
    const text = await fs.readFile(file, "utf8");
    const exports = TS_EXTENSIONS.has(ext) ? extractTsExports(text) : extractPythonExports(text);
    if (exports.length > 0) {
      results.push({ file, exports });
    }
  }
  return results;
}
