import fs from "node:fs/promises";
import path from "node:path";
import { buildImportGraph } from "./importGraph";
import { scanManifests } from "./manifestScanner";
import { discoverTestCommands } from "./testCommandDiscovery";
import { extractExportedSymbols } from "./symbolTable";

export interface RepoIndex {
  root: string;
  files: string[];
  manifests: Awaited<ReturnType<typeof scanManifests>>;
  importGraph: Awaited<ReturnType<typeof buildImportGraph>>;
  testCommands: ReturnType<typeof discoverTestCommands>;
  symbols: Awaited<ReturnType<typeof extractExportedSymbols>>;
}

const IGNORE_DIRS = new Set([".git", "node_modules", "dist", "build", "out", "venv", ".venv", "tmp"]);

async function walk(root: string): Promise<string[]> {
  const results: string[] = [];
  const entries = await fs.readdir(root, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      if (IGNORE_DIRS.has(entry.name)) {
        continue;
      }
      const nested = await walk(fullPath);
      results.push(...nested);
    } else {
      results.push(fullPath);
    }
  }
  return results;
}

export async function buildRepoIndex(root: string): Promise<RepoIndex> {
  const files = await walk(root);
  const manifests = await scanManifests(root);
  const importGraph = await buildImportGraph(files);
  const testCommands = discoverTestCommands(manifests);
  const symbols = await extractExportedSymbols(files);

  return { root, files, manifests, importGraph, testCommands, symbols };
}
