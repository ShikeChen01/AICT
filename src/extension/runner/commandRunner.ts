import { spawn } from "node:child_process";
import type { CommandAllowlist } from "../policy/commandAllowlist";
import { isCommandAllowed } from "../policy/commandAllowlist";
import { truncateOutput } from "./outputTruncation";

export interface CommandSpec {
  command: string;
  args?: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  timeoutMs?: number;
  maxOutputBytes?: number;
  allowlist?: CommandAllowlist;
}

export interface CommandResult {
  code: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
}

export function runCommand(spec: CommandSpec): Promise<CommandResult> {
  if (spec.allowlist && !isCommandAllowed(spec.command, spec.allowlist)) {
    return Promise.resolve({
      code: null,
      signal: null,
      stdout: "",
      stderr: `Command not allowlisted: ${spec.command}`,
      durationMs: 0,
      timedOut: false,
    });
  }

  return new Promise((resolve) => {
    const start = Date.now();
    const child = spawn(spec.command, spec.args ?? [], {
      cwd: spec.cwd,
      env: spec.env ?? process.env,
      shell: spec.args == null || spec.args.length == 0,
    });

    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const timeoutMs = spec.timeoutMs ?? 60_000;
    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, timeoutMs);

    child.stdout?.on("data", (data) => {
      stdout += data.toString();
    });
    child.stderr?.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("close", (code, signal) => {
      clearTimeout(timeout);
      const maxBytes = spec.maxOutputBytes ?? 200_000;
      resolve({
        code,
        signal,
        stdout: truncateOutput(stdout, maxBytes),
        stderr: truncateOutput(stderr, maxBytes),
        durationMs: Date.now() - start,
        timedOut,
      });
    });
  });
}
