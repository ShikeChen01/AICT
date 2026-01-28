import { spawn } from "node:child_process";
import { truncateOutput } from "src/extension/runner/outputTruncation";

// Command runner: execute a single command with output capture and timeout controls.
export type CommandSpec = {
  command: string;
  cwd: string;
  env?: NodeJS.ProcessEnv;
  timeoutMs?: number;
  maxOutputBytes?: number;
  onOutput?: (chunk: string, stream: "stdout" | "stderr") => void;
};

export type CommandResult = {
  command: string;
  code: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
};

export type CommandRunner = {
  runCommand: (spec: CommandSpec) => Promise<CommandResult>;
};

const runCommand = (spec: CommandSpec): Promise<CommandResult> =>
  new Promise((resolve) => {
    const start = Date.now();
    const child = spawn(spec.command, {
      cwd: spec.cwd,
      env: spec.env ?? process.env,
      shell: true,
    });

    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const maxOutputBytes = spec.maxOutputBytes ?? 256 * 1024;

    const handleData = (chunk: Buffer, stream: "stdout" | "stderr") => {
      const text = chunk.toString("utf8");
      if (stream === "stdout") {
        stdout += text;
      } else {
        stderr += text;
      }
      spec.onOutput?.(text, stream);
    };

    child.stdout?.on("data", (chunk: Buffer) => handleData(chunk, "stdout"));
    child.stderr?.on("data", (chunk: Buffer) => handleData(chunk, "stderr"));

    const timeout = spec.timeoutMs
      ? setTimeout(() => {
          timedOut = true;
          child.kill("SIGTERM");
        }, spec.timeoutMs)
      : null;

    child.on("close", (code, signal) => {
      timeout?.unref?.();
      if (timeout) {
        clearTimeout(timeout);
      }

      resolve({
        command: spec.command,
        code,
        signal,
        stdout: truncateOutput(stdout, maxOutputBytes),
        stderr: truncateOutput(stderr, maxOutputBytes),
        durationMs: Date.now() - start,
        timedOut,
      });
    });
  });

export { runCommand };
