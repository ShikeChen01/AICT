import assert from "node:assert/strict";
import { test } from "node:test";
import { truncateOutput } from "../../src/extension/runner/outputTruncation";

test("truncateOutput trims large outputs and keeps marker", () => {
  const input = `HEAD-${"m".repeat(200)}-TAIL`;
  const output = truncateOutput(input, 80);
  assert.equal(output.includes("...truncated..."), true);
  assert.equal(output.includes("HEAD-"), true);
  assert.equal(output.includes("-TAIL"), true);
});
