import assert from "node:assert/strict";
import path from "node:path";
import { test } from "node:test";
import { defaultCommandAllowlist, isCommandAllowed } from "../../src/extension/policy/commandAllowlist";
import { PolicyEngine } from "../../src/extension/policy/policyEngine";
import { ScopeFence, isPathAllowed } from "../../src/extension/policy/scopeFence";

test("command allowlist checks exact and prefix matches", () => {
  assert.equal(isCommandAllowed("npm test", defaultCommandAllowlist), true);
  assert.equal(isCommandAllowed("npm run test", defaultCommandAllowlist), true);
  assert.equal(isCommandAllowed("rm -rf /", defaultCommandAllowlist), false);
});

test("scope fence allows and denies paths", () => {
  const root = path.join(process.cwd(), "workspace");
  const fence = new ScopeFence({
    root,
    allowedPaths: ["src"],
    forbiddenPaths: ["src/secret"],
  });

  assert.equal(isPathAllowed("src/index.ts", fence), true);
  assert.equal(isPathAllowed("src/secret/keys.ts", fence), false);
  assert.equal(isPathAllowed("docs/readme.md", fence), false);
});

test("policy engine blocks disallowed commands", () => {
  const engine = new PolicyEngine({
    commandAllowlist: { exact: [], prefixes: [], regexes: [] },
  });

  const decision = engine.evaluate({ command: "echo ok" });
  assert.equal(decision.allowed, false);
  assert.equal(decision.reasons.length > 0, true);
});
