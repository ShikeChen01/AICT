import assert from "node:assert/strict";
import { test } from "node:test";
import { runCommand } from "../../src/extension/runner/commandRunner";

test("runCommand denies non-allowlisted commands", async () => {
  const result = await runCommand({
    command: "echo hello",
    allowlist: { exact: [], prefixes: [], regexes: [] },
  });

  assert.equal(result.code, null);
  assert.equal(result.stderr.includes("not allowlisted"), true);
});
