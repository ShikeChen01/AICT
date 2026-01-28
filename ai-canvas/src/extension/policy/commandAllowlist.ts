import { minimatch } from "minimatch";

export type CommandAllowlistConfig = {
  patterns: string[];
};

export class CommandAllowlist {
  private readonly patterns: string[];

  constructor(config?: Partial<CommandAllowlistConfig>) {
    this.patterns = config?.patterns ?? [
      "npm test",
      "npm run *",
      "pnpm test",
      "pnpm run *",
      "yarn test",
      "yarn run *",
      "pytest*",
      "python -m pytest*",
    ];
  }

  isCommandAllowed(command: string): boolean {
    return this.patterns.some((pattern) => minimatch(command, pattern));
  }
}

export const isCommandAllowed = (command: string, allowlist?: CommandAllowlist): boolean => {
  if (!allowlist) {
    return true;
  }
  return allowlist.isCommandAllowed(command);
};
