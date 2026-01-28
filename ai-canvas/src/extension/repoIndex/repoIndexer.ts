import * as path from "node:path";
import fg from "fast-glob";
import type { RepoIndex } from "src/shared/types/rpc";
import { scanManifests } from "src/extension/repoIndex/manifestScanner";
import { buildImportGraph } from "src/extension/repoIndex/importGraph";
import { extractExportedSymbols } from "src/extension/repoIndex/symbolTable";

// Repo indexer: scan files + manifests, then build import graph and symbol table.
export type RepoIndexService = {
  buildRepoIndex: (root: string) => Promise<RepoIndex>;
};

export const buildRepoIndex = async (root: string): Promise<RepoIndex> => {
  const files = await fg(["**/*"], {
    cwd: root,
    dot: true,
    onlyFiles: true,
    ignore: ["**/node_modules/**", "**/.git/**", "**/dist/**", "**/out/**"],
    absolute: true,
  });

  const manifests = await scanManifests(root);
  const importGraph = await buildImportGraph(files);
  const symbols = await extractExportedSymbols(files);

  return {
    root: path.resolve(root),
    files,
    manifests,
    import_graph: importGraph,
    symbols,
    updated_at: new Date().toISOString(),
  };
};

export const repoIndexer: RepoIndexService = {
  buildRepoIndex,
};
