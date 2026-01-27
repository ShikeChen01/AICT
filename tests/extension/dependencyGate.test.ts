import assert from "node:assert/strict";
import { test } from "node:test";
import { detectDependencyChanges } from "../../src/extension/policy/dependencyGate";

test("detectDependencyChanges flags manifest edits", () => {
  const diff = [
    "diff --git a/package.json b/package.json",
    "index 111..222 100644",
    "--- a/package.json",
    "+++ b/package.json",
    "@@ -1 +1 @@",
    "-{}",
    '+{"dependencies":{"zod":"^3.0.0"}}',
  ].join("\n");

  const changes = detectDependencyChanges(diff);
  assert.equal(changes.some((entry) => entry.type == "manifest"), true);
});

test("detectDependencyChanges flags lockfile edits", () => {
  const diff = [
    "diff --git a/yarn.lock b/yarn.lock",
    "index 111..222 100644",
    "--- a/yarn.lock",
    "+++ b/yarn.lock",
  ].join("\n");

  const changes = detectDependencyChanges(diff);
  assert.equal(changes.some((entry) => entry.type == "lockfile"), true);
});
