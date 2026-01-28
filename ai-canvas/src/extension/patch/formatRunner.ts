import type { CommandRunner } from "src/extension/runner/commandRunner";
import type { PolicyEngine } from "src/extension/policy/policyEngine";

export type FormatResult = {
  command: string;
  code: number | null;
  stdout: string;
  stderr: string;
};

export const runFormatters = async (
  commands: string[],
  root: string,
  runner: CommandRunner,
  policy: PolicyEngine,
): Promise<FormatResult[]> => {
  const results: FormatResult[] = [];

  for (const command of commands) {
    const decision = policy.evaluate({ kind: "applyPatch", command });
    if (!decision.allow) {
      throw new Error(`Formatter command denied: ${decision.reasons.join("; ")}`);
    }

    const result = await runner.runCommand({
      command,
      cwd: root,
      timeoutMs: 5 * 60 * 1000,
      maxOutputBytes: 64 * 1024,
    });

    results.push({
      command,
      code: result.code,
      stdout: result.stdout,
      stderr: result.stderr,
    });
  }

  return results;
};
