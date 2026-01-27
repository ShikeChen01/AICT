import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { loadWorkspaceState, saveWorkspaceState } from "../../src/extension/storage/workspaceStore";
import { loadCache, saveCache } from "../../src/extension/storage/cacheStore";

async function createTempDir(): Promise<string> {
  return fs.mkdtemp(path.join(os.tmpdir(), "aict-test-"));
}

test("workspace store loads defaults when missing", async () => {
  const root = await createTempDir();
  const state = await loadWorkspaceState(root);
  assert.equal(state.entities.length, 0);
  assert.equal(state.version, 1);
});

test("workspace store saves and loads data", async () => {
  const root = await createTempDir();
  await saveWorkspaceState(root, {
    version: 1,
    entities: [
      {
        id: "1",
        type: "bucket",
        name: "Root",
        purpose: "Test",
        exports: [],
        imports: [],
        deps: [],
        children: [],
      },
    ],
  });

  const state = await loadWorkspaceState(root);
  assert.equal(state.entities.length, 1);
  assert.equal(state.entities[0].id, "1");
});

test("cache store saves and loads data", async () => {
  const root = await createTempDir();
  await saveCache(root, { version: 1, repoIndex: { files: ["a.ts"] } });
  const cache = await loadCache(root);
  assert.equal(cache.version, 1);
  assert.deepEqual(cache.repoIndex, { files: ["a.ts"] });
});
