import { spawn } from "node:child_process";
import type { CommandAllowlist } from "../policy/commandAllowlist";
import { isCommandAllowed } from "../policy/commandAllowlist";

export interface FormatRunResult {
  command: string;
  code: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
}

export async function runFormatters(
  commands: string[],
  options: { cwd: string; allowlist: CommandAllowlist },
): Promise<FormatRunResult[]> {
  const results: FormatRunResult[] = [];
  for (const command of commands) {
    if (!isCommandAllowed(command, options.allowlist)) {
      throw new Error(`Formatter command not allowlisted: ${command}`);
    }
    results.push(await runCommand(command, options.cwd));
  }
  return results;
}

function runCommand(command: string, cwd: string): Promise<FormatRunResult> {
  return new Promise((resolve) => {
    const start = Date.now();
    const child = spawn(command, { cwd, shell: true, env: process.env });
    let stdout = "";
    let stderr = "";

    child.stdout?.on("data", (data) => {
      stdout += data.toString();
    });
    child.stderr?.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("close", (code) => {
      resolve({
        command,
        code,
        stdout,
        stderr,
        durationMs: Date.now() - start,
      });
    });
  });
}
