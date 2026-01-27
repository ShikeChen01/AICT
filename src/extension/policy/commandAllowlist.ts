export interface CommandAllowlist {
  exact: string[];
  prefixes: string[];
  regexes: RegExp[];
}

export const defaultCommandAllowlist: CommandAllowlist = {
  exact: ["npm test", "pnpm test", "yarn test", "pytest", "python -m pytest"],
  prefixes: ["npm ", "pnpm ", "yarn ", "pytest", "python -m pytest", "node "],
  regexes: [],
};

export function isCommandAllowed(command: string, allowlist: CommandAllowlist): boolean {
  const trimmed = command.trim();
  if (allowlist.exact.some((entry) => entry === trimmed)) {
    return true;
  }
  if (allowlist.prefixes.some((prefix) => trimmed.startsWith(prefix))) {
    return true;
  }
  return allowlist.regexes.some((regex) => regex.test(trimmed));
}
