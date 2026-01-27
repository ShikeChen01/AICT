import assert from "node:assert/strict";
import { test } from "node:test";
import { validateRpcRequest, validateRpcResponse } from "../../src/extension/rpc/rpcValidation";

test("validateRpcRequest accepts valid payloads", () => {
  const result = validateRpcRequest({ id: "1", method: "runTests", params: { foo: "bar" } });
  assert.equal(result.ok, true);
});

test("validateRpcRequest rejects invalid payloads", () => {
  const result = validateRpcRequest({ id: "1" });
  assert.equal(result.ok, false);
});

test("validateRpcResponse accepts valid payloads", () => {
  const result = validateRpcResponse({ id: "1", ok: true, result: { ok: true } });
  assert.equal(result.ok, true);
});
