import type { ManifestInfo } from "src/shared/types/rpc";

export type TestCommand = {
  command: string;
  source: string;
};

export const discoverTestCommands = (manifests: ManifestInfo[]): TestCommand[] => {
  const commands: TestCommand[] = [];

  for (const manifest of manifests) {
    if (manifest.kind !== "package.json") {
      continue;
    }

    const scripts = manifest.scripts ?? {};
    if (scripts.test) {
      commands.push({ command: "npm test", source: manifest.path });
    }

    for (const [name] of Object.entries(scripts)) {
      if (name !== "test" && name.startsWith("test")) {
        commands.push({ command: `npm run ${name}`, source: manifest.path });
      }
    }
  }

  return commands;
};
