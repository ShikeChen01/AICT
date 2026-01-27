import path from "node:path";
import type { ManifestInfo } from "./manifestScanner";

export interface TestCommand {
  command: string;
  cwd: string;
  source: string;
}

export function discoverTestCommands(manifests: ManifestInfo[]): TestCommand[] {
  const commands: TestCommand[] = [];
  for (const manifest of manifests) {
    if (manifest.type === "package-json" && manifest.scripts?.test) {
      commands.push({
        command: `npm run test`,
        cwd: path.dirname(manifest.path),
        source: manifest.path,
      });
    }
    if (manifest.type === "pyproject") {
      commands.push({
        command: "pytest",
        cwd: path.dirname(manifest.path),
        source: manifest.path,
      });
    }
    if (manifest.type === "requirements") {
      commands.push({
        command: "pytest",
        cwd: path.dirname(manifest.path),
        source: manifest.path,
      });
    }
  }
  return commands;
}
