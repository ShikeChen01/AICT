# ADR-008: Firebase Auth with Separate GitHub Credentials

## Status

Accepted

## Context

AICT needs two types of authentication:
1. **User identity** — who is this user? Are they allowed to access this project?
2. **GitHub access** — create repos, clone, push, open PRs on behalf of the user.

Options for combining these:
1. **GitHub OAuth for both** — user logs in with GitHub, and the OAuth token is used for both identity and git operations. Simple but couples identity to a git provider.
2. **Firebase for identity + GitHub PAT stored separately** — user logs in with Google via Firebase, and provides a GitHub Personal Access Token in their settings.
3. **Firebase for identity + GitHub App integration** — more complex, supports organization-level access.

## Decision

**Firebase Authentication (Google OAuth) for user identity. GitHub Personal Access Token stored per-user as a separate credential.**

- Users log in with Google via Firebase. The Firebase ID token is sent as `Authorization: Bearer <token>` on every API request.
- The backend verifies the token with Firebase Admin SDK (`get_current_user` dependency).
- The GitHub PAT is stored in `users.github_token` and configured via `PATCH /api/v1/auth/me` in the User Settings page.
- The backend uses the GitHub PAT for `GitService` operations (repo creation, cloning, push).
- The API never returns the token value — only `github_token_set: bool`.

## Consequences

**Positive:**
- User identity is decoupled from the git provider. Users could use GitLab, Bitbucket, or self-hosted git in the future without changing the auth system.
- Firebase handles OAuth complexity, token refresh, and session management.
- The GitHub PAT is a well-understood credential model. Users control its scope and can revoke it independently.
- No GitHub App registration or organization approval required.

**Negative:**
- Users must manually create and paste a GitHub PAT. Friction compared to OAuth-based GitHub login.
- The PAT is stored in the database (not encrypted at rest beyond database-level encryption). Should be encrypted at the application level for production hardening.
- Firebase is a hard dependency — no easy swap to another auth provider without rewriting the `get_current_user` flow.
- Two separate credential flows increase onboarding complexity.
