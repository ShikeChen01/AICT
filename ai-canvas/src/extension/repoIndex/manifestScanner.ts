import * as fs from "node:fs/promises";
import * as path from "node:path";
import fg from "fast-glob";
import type { ManifestInfo } from "src/shared/types/rpc";

const parsePackageJson = async (filePath: string): Promise<ManifestInfo | null> => {
  try {
    const raw = await fs.readFile(filePath, "utf8");
    const json = JSON.parse(raw) as { scripts?: Record<string, string> };
    return {
      path: filePath,
      kind: "package.json",
      scripts: json.scripts ?? {},
    };
  } catch {
    return null;
  }
};

const parseRequirements = async (filePath: string): Promise<ManifestInfo> => ({
  path: filePath,
  kind: "requirements.txt",
  scripts: {},
});

const parsePyproject = async (filePath: string): Promise<ManifestInfo> => ({
  path: filePath,
  kind: "pyproject.toml",
  scripts: {},
});

export const scanManifests = async (root: string): Promise<ManifestInfo[]> => {
  const patterns = ["**/package.json", "**/pyproject.toml", "**/requirements.txt"];
  const entries = await fg(patterns, {
    cwd: root,
    dot: true,
    ignore: ["**/node_modules/**", "**/.git/**", "**/dist/**"],
    absolute: true,
  });

  const manifests: ManifestInfo[] = [];
  for (const entry of entries) {
    const name = path.basename(entry);
    if (name === "package.json") {
      const manifest = await parsePackageJson(entry);
      if (manifest) {
        manifests.push(manifest);
      }
      continue;
    }

    if (name === "pyproject.toml") {
      manifests.push(await parsePyproject(entry));
      continue;
    }

    if (name === "requirements.txt") {
      manifests.push(await parseRequirements(entry));
    }
  }

  return manifests;
};
