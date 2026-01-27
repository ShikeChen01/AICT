import assert from "node:assert/strict";
import path from "node:path";
import { test } from "node:test";
import { validateUnifiedDiff } from "../../src/extension/patch/diffValidator";
import { ScopeFence } from "../../src/extension/policy/scopeFence";

test("validateUnifiedDiff rejects empty diffs", () => {
  const result = validateUnifiedDiff("");
  assert.equal(result.ok, false);
});

test("validateUnifiedDiff accepts in-scope diffs", () => {
  const diff = [
    "--- a/src/index.ts",
    "+++ b/src/index.ts",
    "@@ -1 +1 @@",
    "-const a = 1;",
    "+const a = 2;",
  ].join("\n");

  const fence = new ScopeFence({ root: path.join(process.cwd(), "workspace"), allowedPaths: ["src"] });
  const result = validateUnifiedDiff(diff, fence);
  assert.equal(result.ok, true);
});

test("validateUnifiedDiff rejects out-of-scope diffs", () => {
  const diff = [
    "--- a/docs/readme.md",
    "+++ b/docs/readme.md",
    "@@ -1 +1 @@",
    "-Old",
    "+New",
  ].join("\n");

  const fence = new ScopeFence({ root: path.join(process.cwd(), "workspace"), allowedPaths: ["src"] });
  const result = validateUnifiedDiff(diff, fence);
  assert.equal(result.ok, false);
});
