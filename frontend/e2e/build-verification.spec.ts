/**
 * Build Verification E2E Test
 *
 * Verifies the full AICT stack end-to-end:
 *   1. Login via test login endpoint
 *   2. Set GitHub token on user profile
 *   3. Import test repository
 *   4. Wait for manager agent to be created
 *   5. Send a "do nothing" message to the manager
 *   6. Verify the message was accepted (202)
 *   7. If WAIT_FOR_AGENT_RESPONSE=true, wait for the agent to open a session
 *      (proves the LLM pipeline is processing)
 *
 * Required environment variables:
 *   GITHUB_TEST_TOKEN              GitHub PAT used as the user's cloning credential
 *   GITHUB_TEST_REPOSITORY_LINK    Full HTTPS URL of the test repo to import
 *   TEST_LOGIN_EMAIL               Test login email (default: aicttest@aict.com)
 *   TEST_LOGIN_PASSWORD            Test login password
 *
 * Optional:
 *   BACKEND_URL                    Backend base URL (default: http://localhost:8000)
 *   WAIT_FOR_AGENT_RESPONSE        Set to 'true' to also wait for a session (needs LLM keys)
 */

import { test, expect } from '@playwright/test';

// ── Config ────────────────────────────────────────────────────────────────────

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');
const GITHUB_TEST_TOKEN = process.env.GITHUB_TEST_TOKEN ?? '';
const GITHUB_TEST_REPOSITORY_LINK = process.env.GITHUB_TEST_REPOSITORY_LINK ?? '';
const TEST_LOGIN_EMAIL = process.env.TEST_LOGIN_EMAIL || 'aicttest@aict.com';
const TEST_LOGIN_PASSWORD = process.env.TEST_LOGIN_PASSWORD ?? '';
const WAIT_FOR_AGENT_RESPONSE = process.env.WAIT_FOR_AGENT_RESPONSE === 'true';

// ── Helpers ───────────────────────────────────────────────────────────────────

interface Agent {
  id: string;
  role: string;
  status: string;
}

interface Session {
  id: string;
}

async function pollUntil<T>(
  fn: () => Promise<T | null>,
  timeoutMs: number,
  intervalMs = 4_000,
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown;
  while (Date.now() < deadline) {
    try {
      const result = await fn();
      if (result !== null) return result;
    } catch (err) {
      lastError = err;
    }
    await new Promise<void>((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`pollUntil timed out after ${timeoutMs}ms${lastError ? ` (last error: ${lastError})` : ''}`);
}

// ── Test ──────────────────────────────────────────────────────────────────────

test.describe('Build Verification', () => {
  // 5 minutes — repo import + agent spawn + optional LLM round-trip
  test.setTimeout(5 * 60 * 1000);

  test('import test repository and verify agent pipeline', async ({ request }) => {
    // ── Precondition check ────────────────────────────────────────────────────
    if (!GITHUB_TEST_TOKEN) {
      test.skip(true, 'GITHUB_TEST_TOKEN not set — skipping build verification');
      return;
    }
    if (!GITHUB_TEST_REPOSITORY_LINK) {
      test.skip(true, 'GITHUB_TEST_REPOSITORY_LINK not set — skipping build verification');
      return;
    }
    if (!TEST_LOGIN_PASSWORD) {
      test.skip(true, 'TEST_LOGIN_PASSWORD not set — skipping build verification');
      return;
    }

    // ── Step 1: Obtain API token via test login ───────────────────────────────
    const loginRes = await request.post(`${BACKEND_URL}/testfads89213xlogin`, {
      data: { email: TEST_LOGIN_EMAIL, password: TEST_LOGIN_PASSWORD },
    });
    expect(loginRes.ok(), `Test login failed: ${loginRes.status()} ${await loginRes.text()}`).toBeTruthy();
    const { token } = await loginRes.json() as { token: string };
    const headers = { Authorization: `Bearer ${token}` };

    // ── Step 2: Set GitHub token on user profile ──────────────────────────────
    const patchRes = await request.patch(`${BACKEND_URL}/api/v1/auth/me`, {
      headers,
      data: { github_token: GITHUB_TEST_TOKEN },
    });
    expect(patchRes.ok(), `PATCH /auth/me failed: ${patchRes.status()}`).toBeTruthy();

    // ── Step 3: Import test repository ───────────────────────────────────────
    const repoLabel = `build-verify-${Date.now()}`;
    const importRes = await request.post(`${BACKEND_URL}/api/v1/repositories/import`, {
      headers,
      data: {
        name: repoLabel,
        description: 'Automated build verification — safe to delete',
        code_repo_url: GITHUB_TEST_REPOSITORY_LINK,
      },
    });
    expect(
      importRes.status(),
      `Repository import failed: ${importRes.status()} ${await importRes.text()}`
    ).toBe(201);
    const repo = await importRes.json() as { id: string; name: string };
    const projectId = repo.id;
    console.log(`[BV] Imported repository: id=${projectId} name=${repo.name}`);

    try {
      // ── Step 4: Wait for manager agent to be created ──────────────────────
      const manager = await pollUntil<Agent>(async () => {
        const res = await request.get(
          `${BACKEND_URL}/api/v1/agents?project_id=${projectId}`,
          { headers }
        );
        if (!res.ok()) return null;
        const agents = await res.json() as Agent[];
        return agents.find((a) => a.role === 'manager') ?? null;
      }, 60_000);

      console.log(`[BV] Manager agent found: id=${manager.id} status=${manager.status}`);

      // ── Step 5: Send build verification message ───────────────────────────
      const msgRes = await request.post(`${BACKEND_URL}/api/v1/messages/send`, {
        headers,
        data: {
          project_id: projectId,
          target_agent_id: manager.id,
          content:
            'This is an automated build verification test. ' +
            'Please acknowledge this message briefly and do nothing else.',
        },
      });
      expect(
        msgRes.status(),
        `Message send failed: ${msgRes.status()} ${await msgRes.text()}`
      ).toBe(202);
      console.log('[BV] Verification message sent (202 accepted)');

      // ── Step 6 (optional): Wait for agent to open a session ───────────────
      // Only run when WAIT_FOR_AGENT_RESPONSE=true; requires real LLM API keys.
      if (WAIT_FOR_AGENT_RESPONSE) {
        console.log('[BV] Waiting for agent session (WAIT_FOR_AGENT_RESPONSE=true)...');
        const sessions = await pollUntil<Session[]>(async () => {
          const res = await request.get(
            `${BACKEND_URL}/api/v1/sessions?project_id=${projectId}&agent_id=${manager.id}`,
            { headers }
          );
          if (!res.ok()) return null;
          const data = await res.json() as Session[];
          return data.length > 0 ? data : null;
        }, 120_000, 5_000);

        console.log(`[BV] Agent session created: id=${sessions[0].id}`);
        expect(sessions.length).toBeGreaterThan(0);
      }

    } finally {
      // ── Step 7: Cleanup — delete the test repository from AICT ───────────
      const delRes = await request.delete(
        `${BACKEND_URL}/api/v1/repositories/${projectId}`,
        { headers }
      );
      if (!delRes.ok()) {
        console.warn(`[BV] Cleanup: DELETE /repositories/${projectId} returned ${delRes.status()}`);
      } else {
        console.log(`[BV] Cleanup: repository ${projectId} deleted`);
      }
    }
  });
});
