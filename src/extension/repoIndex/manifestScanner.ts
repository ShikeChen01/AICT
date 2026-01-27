import fs from "node:fs/promises";
import path from "node:path";

export type ManifestType = "package-json" | "pyproject" | "requirements" | "pipfile" | "unknown";

export interface ManifestInfo {
  path: string;
  type: ManifestType;
  scripts?: Record<string, string>;
  raw?: string;
}

const MANIFEST_NAMES = new Set(["package.json", "pyproject.toml", "requirements.txt", "Pipfile"]);
const IGNORE_DIRS = new Set([".git", "node_modules", "dist", "build", "out", "venv", ".venv", "tmp"]);

async function walk(root: string): Promise<string[]> {
  const results: string[] = [];
  const entries = await fs.readdir(root, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isDirectory()) {
      if (IGNORE_DIRS.has(entry.name)) {
        continue;
      }
      const nested = await walk(path.join(root, entry.name));
      results.push(...nested);
    } else if (MANIFEST_NAMES.has(entry.name)) {
      results.push(path.join(root, entry.name));
    }
  }
  return results;
}

export async function scanManifests(root: string): Promise<ManifestInfo[]> {
  const files = await walk(root);
  const manifests: ManifestInfo[] = [];

  for (const filePath of files) {
    const fileName = path.basename(filePath);
    const raw = await fs.readFile(filePath, "utf8");

    if (fileName === "package.json") {
      const data = JSON.parse(raw) as { scripts?: Record<string, string> };
      manifests.push({ path: filePath, type: "package-json", scripts: data.scripts, raw });
      continue;
    }

    if (fileName === "pyproject.toml") {
      manifests.push({ path: filePath, type: "pyproject", raw });
      continue;
    }

    if (fileName === "requirements.txt") {
      manifests.push({ path: filePath, type: "requirements", raw });
      continue;
    }

    if (fileName === "Pipfile") {
      manifests.push({ path: filePath, type: "pipfile", raw });
      continue;
    }

    manifests.push({ path: filePath, type: "unknown", raw });
  }

  return manifests;
}
