import { minimatch } from "minimatch";

export type CommandBlocklistConfig = {
  patterns: string[];
};

export class CommandBlocklist {
  private readonly patterns: string[];

  constructor(config?: Partial<CommandBlocklistConfig>) {
    this.patterns = config?.patterns ?? [];
  }

  isCommandBlocked(command: string): boolean {
    return this.patterns.some((pattern) => minimatch(command, pattern));
  }
}

export const isCommandAllowed = (command: string, blocklist?: CommandBlocklist): boolean => {
  if (!blocklist) {
    return true;
  }
  return !blocklist.isCommandBlocked(command);
};
