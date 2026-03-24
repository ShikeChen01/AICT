# OpenAI OAuth Integration Design

> **Status:** Ready for review
> **Date:** 2026-03-24
> **Scope:** Phase 1 of the ChatGPT OAuth pivot. Agent architecture redesign is a separate spec.

---

## 1. Problem & Motivation

AICT currently pays for all LLM inference. This is unsustainable. Competing with Claude Code on coding, and with E2B/Daytona on sandboxes, requires a pricing pivot.

**The move:** users bring their own ChatGPT/OpenAI account via OAuth. AICT charges only for sandbox compute (the existing tier system: Free/$20/$50). LLM inference costs route through the user's OpenAI subscription.

This mirrors Codex's model: authenticate with OpenAI, run agents on their dime.

### Why OpenAI OAuth (not just BYOK API keys)?

Per-user API keys (BYOK) already exist, but OAuth is better for most users:

- **No key management** - users sign in with their OpenAI account, done
- **Uses existing subscription** - ChatGPT Plus/Pro users already pay; no extra API billing setup
- **Lower friction** - one click vs copy-pasting `sk-...` keys
- **Trust** - OAuth is a recognized auth pattern; pasting API keys feels sketchy to non-developers

BYOK stays as a power-user escape hatch for Claude, Gemini, Moonshot, and users who prefer raw API keys.

---

## 2. Approach: Firebase Custom Tokens as Bridge

The key insight: **every user ends up with a Firebase JWT**, regardless of how they signed in.

When a user authenticates via OpenAI OAuth, the backend:
1. Exchanges the OAuth code for OpenAI tokens
2. Creates/finds the AICT User
3. Mints a **Firebase Custom Token** (`firebase_admin.auth.create_custom_token`)
4. Returns it to the frontend
5. Frontend calls `signInWithCustomToken` to get a real Firebase ID token

**Result:** zero changes to the existing auth middleware, ProtectedRoute, API client, or WebSocket auth. The backend still receives and validates Firebase JWTs on every request. The only new code is the OAuth handshake itself.

### Why not replace Firebase?

Firebase auth is deeply embedded: the frontend's `AuthContext`, the backend's `verify_token` / `get_current_user`, the `firebase_uid` column on `User`. Replacing it would be a rewrite with no user-facing benefit. Instead, we add OpenAI as a federation layer that outputs Firebase tokens.

---

## 3. Data Model

### 3.1 New table: `user_oauth_connections`

Stores OAuth token state per user per provider. Designed to support future OAuth providers (GitHub, Google Workspace, etc.) without schema changes.

```
user_oauth_connections
├── id                  UUID PK
├── user_id             UUID FK → users NOT NULL
├── provider            VARCHAR(50) NOT NULL  -- "openai" (extensible)
├── provider_user_id    VARCHAR(255) NOT NULL -- OpenAI user ID
├── provider_email      VARCHAR(255)          -- email from OpenAI profile
├── access_token        TEXT NOT NULL          -- Fernet-encrypted
├── refresh_token       TEXT                   -- Fernet-encrypted (nullable if provider doesn't issue one)
├── token_expires_at    TIMESTAMPTZ           -- when access_token expires
├── scopes              TEXT                   -- JSON array of granted scopes
├── is_valid            BOOLEAN DEFAULT TRUE   -- flagged false on auth failure
├── created_at          TIMESTAMPTZ NOT NULL
├── updated_at          TIMESTAMPTZ NOT NULL
├── UNIQUE(user_id, provider)
└── UNIQUE(provider, provider_user_id)
```

`user_id` is NOT NULL. The User row is always created before the OAuthConnection (Flow A creates the user first, Flow B already has one). No mid-flow unlinked state.

### 3.2 User model changes

The migration widens `users.firebase_uid` from `String(128)` to `String(255)`. This column now serves as a polymorphic federation key (Firebase UID or `openai:{provider_user_id}`), and needs headroom for future provider ID formats.

Add `openai_connected` as a derived property (exists in `user_oauth_connections`), not a column. The `_to_user_response` helper needs a DB session to query the connection table — refactor it to accept `db: AsyncSession` and eagerly load the flag.

The `firebase_uid` for OpenAI-only users uses the format `openai:{provider_user_id}` to guarantee uniqueness (colons never appear in real Firebase UIDs).

### 3.3 Email collision handling

The `users.email` column has a unique constraint. When a user signs in via OpenAI, their OpenAI email may already belong to an existing Firebase (Google) user. This is handled in Flow A:

- After fetching the OpenAI profile, check if a User with that email already exists.
- If so, do NOT auto-create a new user. Return a response telling the frontend: "An account with this email already exists. Please sign in with Google first, then connect your OpenAI account from Settings."
- This prevents duplicate accounts and avoids forced account merging.
- Edge case: if the existing user already has an OpenAI connection, return the same message (they should sign in via their original method).

---

## 4. Auth Flows

### 4.1 Flow A: New user signs in with OpenAI (primary login)

```
Browser                     Backend                         OpenAI
  │                           │                               │
  ├─ GET /auth/openai/login ─►│                               │
  │  (returns redirect URL)   │                               │
  │                           │                               │
  ◄─ 302 redirect ───────────┤                               │
  │                           │                               │
  ├─ User authorizes ─────────┼──────────────────────────────►│
  │                           │                               │
  ◄─ Redirect with code ──────┼───────────────────────────────┤
  │                           │                               │
  ├─ POST /auth/openai/       │                               │
  │    callback {code,state} ►│                               │
  │                           ├─ POST token endpoint ────────►│
  │                           ◄─ {access_token, refresh} ─────┤
  │                           │                               │
  │                           ├─ GET userinfo ────────────────►│
  │                           ◄─ {id, email, name} ───────────┤
  │                           │
  │                           ├─ Create User(firebase_uid="openai:{id}")
  │                           ├─ Create UserOAuthConnection
  │                           ├─ firebase_admin.create_custom_token("openai:{id}")
  │                           │
  ◄─ {firebase_custom_token} ─┤
  │                           │
  ├─ signInWithCustomToken() ─┤  (Firebase client SDK)
  │                           │
  ├─ Normal Firebase JWT flow │
```

### 4.2 Flow B: Existing Firebase user connects OpenAI

Same OAuth redirect/callback, but the callback endpoint receives the user's existing Firebase JWT in the Authorization header. Instead of creating a new User, it links the OAuthConnection to the existing user.

```
POST /auth/openai/callback
  Authorization: Bearer <firebase_jwt>  ← existing user
  Body: {code, state}

Backend:
  1. Verify Firebase JWT → get existing User
  2. Exchange code for tokens
  3. Create UserOAuthConnection(user_id=existing_user.id)
  4. Return {connected: true}  ← no custom token needed, already authed
```

### 4.3 Flow C: Disconnect OpenAI

```
DELETE /auth/openai/disconnect
  Authorization: Bearer <firebase_jwt>

Backend:
  1. Verify user has Firebase (Google) auth as fallback
     - Check firebase_uid does NOT start with "openai:"
     - If it does, reject: "Cannot disconnect your only auth method.
       Link a Google account first."
  2. Delete UserOAuthConnection
  3. LLM calls fall back to BYOK or server-wide keys
```

### 4.4 Flow D: OpenAI-only user links Google account

Users who signed in via OpenAI have `firebase_uid="openai:{id}"` and no Google auth. To add a Google escape path (so they can later disconnect OpenAI):

1. User clicks "Link Google Account" in Settings
2. Frontend calls `linkWithPopup(auth.currentUser, GoogleAuthProvider)` (Firebase client SDK)
3. Firebase links the Google credential to their existing custom-token account
4. Backend updates `User.firebase_uid` to the real Firebase UID from the Google credential
5. User now has two auth methods and can disconnect either one

This is a standard Firebase account linking flow. The implementation detail: after `linkWithPopup`, the frontend calls a new `PATCH /auth/link-google` endpoint that receives the Google credential's UID and updates the `firebase_uid` column.

---

## 5. Backend Endpoints

All under `/api/v1/auth/openai/`.

### `GET /auth/openai/login`

Generates the OAuth authorization URL with a CSRF `state` token.

- **State management:** HMAC-signed, self-contained state token. The state encodes the flow type ("login" or "connect"), a nonce, and an expiry timestamp, signed with `secret_encryption_key`. The callback verifies the signature without server-side storage — works across multiple Cloud Run instances.
- **Query params:** `?flow=login` (default) or `?flow=connect`
- **Returns:** `{url: "https://platform.openai.com/oauth/authorize?..."}`

### `POST /auth/openai/callback`

Exchanges the authorization code for tokens.

- **Body:** `{code: string, state: string}`
- **Optional header:** `Authorization: Bearer <firebase_jwt>` (for connect flow)
- **Logic:**
  1. Validate state token (CSRF check)
  2. Exchange code at OpenAI token endpoint
  3. Fetch user profile from OpenAI userinfo endpoint
  4. If connect flow (has Authorization header):
     - Link OAuthConnection to existing user
     - Return `{connected: true}`
  5. If login flow:
     - Check if a User with the OpenAI email already exists (email collision check, see 3.3)
     - If collision: return `{error: "email_exists", message: "..."}`
     - Otherwise: find or create User with `firebase_uid="openai:{provider_user_id}"`
     - Create OAuthConnection
     - Mint Firebase Custom Token
     - Return `{firebase_custom_token: "..."}`

### `GET /auth/openai/status`

Returns the current user's OpenAI connection state.

- **Requires:** Firebase JWT auth
- **Returns:** `{connected: bool, email?: string, scopes?: string[], valid?: bool}`

### `DELETE /auth/openai/disconnect`

Removes the OpenAI connection. Refuses if OpenAI is the user's only auth method.

### `POST /auth/openai/refresh` (internal)

Not a public endpoint. Called internally by the token refresh service before LLM calls. Exposed as a service method, not an API route.

---

## 6. Token Lifecycle

### 6.1 Refresh logic

Before each LLM call that would use an OAuth token:

```python
async def get_valid_openai_token(user_id: UUID, db: AsyncSession) -> str | None:
    conn = await OAuthConnectionRepository.get_by_user_and_provider(db, user_id, "openai")
    if not conn or not conn.is_valid:
        return None

    # Token still valid (with 5-minute buffer)
    if conn.token_expires_at and conn.token_expires_at > utcnow() + timedelta(minutes=5):
        return decrypt(conn.access_token)

    # Refresh needed — use SELECT ... FOR UPDATE to serialize concurrent
    # refresh attempts for the same (user_id, provider). Without this,
    # two agent loops could race: both see expired token, both refresh,
    # and the loser uses a stale rotating refresh token → invalidation.
    conn = await OAuthConnectionRepository.get_for_update(db, user_id, "openai")
    if not conn or not conn.is_valid:
        return None

    # Re-check after lock — another coroutine may have already refreshed
    if conn.token_expires_at and conn.token_expires_at > utcnow() + timedelta(minutes=5):
        return decrypt(conn.access_token)

    if not conn.refresh_token:
        conn.is_valid = False
        await db.commit()
        return None

    try:
        new_tokens = await openai_oauth_client.refresh(decrypt(conn.refresh_token))
        conn.access_token = encrypt(new_tokens.access_token)
        conn.token_expires_at = utcnow() + timedelta(seconds=new_tokens.expires_in)
        if new_tokens.refresh_token:  # rotating refresh tokens
            conn.refresh_token = encrypt(new_tokens.refresh_token)
        await db.commit()
        return new_tokens.access_token
    except OAuthRefreshError:
        conn.is_valid = False
        await db.commit()
        return None
```

### 6.2 Resolution priority in Agent._resolve_user_api_key()

```
1. UserOAuthConnection (provider="openai") → access_token (auto-refreshed)
2. UserAPIKey (provider="openai")          → BYOK static key
3. settings.openai_api_key                 → server-wide fallback
```

The existing `_resolve_user_api_key` method is extended, not replaced. OAuth check is added as a first step before the existing BYOK lookup.

---

## 7. Config Changes

New env vars in `backend/config.py`:

```python
# OpenAI OAuth
openai_oauth_client_id: str = ""
openai_oauth_client_secret: str = ""       # stored securely in env (Cloud Run secrets)
openai_oauth_authorize_url: str = "https://platform.openai.com/oauth/authorize"
openai_oauth_token_url: str = "https://platform.openai.com/oauth/token"
openai_oauth_userinfo_url: str = "https://api.openai.com/v1/me"
openai_oauth_redirect_uri: str = ""        # e.g. https://app.aict.dev/auth/openai/callback
openai_oauth_scopes: str = "openai.api"    # space-separated
```

URLs are configurable because OpenAI's OAuth endpoints may change or differ between environments.

---

## 8. Frontend Changes

### 8.1 Login page

Add "Sign in with OpenAI" button below the existing "Continue with Google":

```
┌─────────────────────────────────┐
│ Login                           │
│                                 │
│ Sign in to continue.            │
│                                 │
│ [🔵 Continue with Google     ]  │
│ [⬛ Sign in with OpenAI      ]  │
│                                 │
│ First time? Get started         │
└─────────────────────────────────┘
```

**Flow:** Click button → `GET /auth/openai/login?flow=login` → redirect to OpenAI → redirect back to `/auth/openai/callback` → backend returns `firebase_custom_token` → frontend calls `signInWithCustomToken(auth, token)` → normal Firebase flow takes over.

### 8.2 New route: `/auth/openai/callback`

A new callback page (similar to `AuthCallbackPage`) that:
1. Extracts `code` and `state` from URL params
2. POSTs them to the backend callback endpoint
3. If login flow: signs in with the returned Firebase Custom Token (using `signInWithCustomToken` from `firebase/auth` — new import)
4. If connect flow: shows success message, redirects to settings
5. On error (including `email_exists`): shows error message with appropriate action button

**Important:** This route must be **outside** `ProtectedRoute` in `App.tsx` (alongside `/login` and `/register`). The user has no Firebase auth yet during the login flow callback.

### 8.3 User Settings — Connected Accounts

New section in `UserSettingsPage` between the profile form and API Keys:

```
┌─────────────────────────────────┐
│ Connected Accounts              │
│                                 │
│ OpenAI  ✅ user@email.com       │
│         [Disconnect]            │
│                                 │
│   — or —                        │
│                                 │
│ OpenAI  [Connect OpenAI Account]│
└─────────────────────────────────┘
```

When connected, OpenAI LLM calls use the OAuth token automatically. The API Keys section still shows the OpenAI BYOK option, but with a note: "OpenAI connected via OAuth. BYOK key is not used while OAuth is active."

### 8.4 AuthContext changes

Add `loginWithOpenAI()` method alongside `loginWithGoogle()`:

```typescript
async loginWithOpenAI() {
  const { url } = await apiClient.get('/auth/openai/login?flow=login');
  window.location.href = url;  // Full page redirect to OpenAI
}
```

The callback page handles the return. `signInWithCustomToken` feeds back into the existing `onAuthStateChanged` listener, so the rest of the auth flow is untouched.

### 8.5 UserProfile type

Add to the `UserProfile` type:
```typescript
openai_connected?: boolean;
openai_email?: string;
```

The `/auth/me` endpoint returns these from the OAuthConnection table.

---

## 9. LLM Routing Changes

### 9.1 New service: `OAuthTokenService`

Lives in `backend/services/oauth_token_service.py`. Responsibilities:
- `get_valid_token(user_id, provider, db)` → decrypted access token or None
- `refresh_if_needed(connection, db)` → refreshes expired tokens
- `revoke(user_id, provider, db)` → marks connection invalid

### 9.2 Agent._resolve_user_api_key() extension

The existing method uses inline imports and instantiates its own `UserAPIKeyRepository`. The OAuth extension follows the same pattern (import `OAuthTokenService` inline, no service injection refactor):

```python
async def _resolve_user_api_key(self) -> str | None:
    owner_id = self._project.owner_id
    provider_name = ProviderRouter().resolve_provider_name(self._resolved_model)

    # 1. Try OAuth token (OpenAI only, for now)
    if provider_name == "openai":
        from backend.services.oauth_token_service import OAuthTokenService
        oauth_token = await OAuthTokenService.get_valid_token(
            self._db, owner_id, "openai"
        )
        if oauth_token:
            return oauth_token

    # 2. Fall back to BYOK (existing logic, unchanged)
    key_provider = _PROVIDER_TO_KEY_PROVIDER.get(provider_name)
    if not key_provider:
        return None
    from backend.config import settings as app_settings
    return await UserAPIKeyRepository.get_decrypted_key(
        self._db, owner_id, key_provider, app_settings.secret_encryption_key
    )
```

The LLM provider doesn't know or care whether the key came from OAuth or BYOK. It's just a string passed to `AsyncOpenAI(api_key=...)`.

---

## 10. Database Migration

Single Alembic migration:

```python
def upgrade():
    # Widen firebase_uid to accommodate "openai:{provider_user_id}" format
    op.alter_column("users", "firebase_uid",
                     existing_type=sa.String(128),
                     type_=sa.String(255))

    op.create_table(
        "user_oauth_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("provider_email", sa.String(255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_conn_user_provider"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_conn_provider_ext_id"),
    )
    op.create_index("ix_oauth_conn_user", "user_oauth_connections", ["user_id"])

def downgrade():
    op.drop_index("ix_oauth_conn_user")
    op.drop_table("user_oauth_connections")
    op.alter_column("users", "firebase_uid",
                     existing_type=sa.String(255),
                     type_=sa.String(128))
```

---

## 11. Security Considerations

1. **CSRF on OAuth flow:** HMAC-signed state token (stateless, works across Cloud Run instances). Includes nonce + expiry. Validated on callback without server-side storage. Expires after 10 minutes.
2. **Token storage:** Access and refresh tokens encrypted at rest with Fernet (same as UserAPIKey). Never logged or returned in API responses.
3. **Scope minimization:** Request only the scopes needed for API access. No write access to user's OpenAI account.
4. **Token revocation:** When user disconnects, tokens are deleted from DB. If OpenAI supports token revocation, call it.
5. **Refresh token rotation:** If OpenAI rotates refresh tokens, store the new one on each refresh.
6. **firebase_uid collision:** The `openai:{id}` prefix prevents collision with real Firebase UIDs (which are alphanumeric, no colons).
7. **Account linking safety:** When connecting OpenAI to an existing account, verify the user is authenticated via Firebase first. Don't allow re-linking to a different user.

---

## 12. What This Spec Does NOT Cover

- **Agent architecture redesign** — hierarchical orchestration replacing flat async loops. Separate spec.
- **Other OAuth providers** — the data model supports them, but only OpenAI is implemented.
- **Team seat management** — existing billing limitation, not related to OAuth.
- **OpenAI API scope limitations** — depends on what OpenAI's OAuth actually grants. If OAuth tokens can't make chat completion calls, the design falls back to BYOK seamlessly (the token refresh will fail, `is_valid` goes false, BYOK takes over).

---

## 13. Open Questions

1. **OpenAI OAuth availability (potential blocker):** As of writing, OpenAI's public OAuth is primarily designed for ChatGPT plugin/action authentication (where OpenAI is the client). There is no confirmed public flow where a third-party app obtains OAuth tokens usable as API keys for `AsyncOpenAI(api_key=...)`. This is the biggest feasibility risk. **Fallback plan:** If OAuth-for-API-access doesn't exist or isn't available, the entire backend/frontend OAuth plumbing still works — it just provides authentication (sign-in with OpenAI identity) without automatic LLM funding. Users would still need BYOK API keys for actual LLM calls. The auth value (one-click sign-in) and the LLM funding value (use your subscription) are separable.

2. **ChatGPT Plus vs API billing:** Does OAuth token usage bill against the user's ChatGPT subscription or their separate API account? This affects the value prop messaging but not the technical implementation.

3. **Rate limits:** OAuth tokens may have different rate limits than API keys. The existing retry/fallback logic in the LLM providers handles 429s, but we may need to surface "your OpenAI account is rate-limited" to the user.

---

## 14. Testing Strategy

- **Unit tests:** OAuthTokenService (refresh logic, expiry handling, encryption round-trip)
- **Unit tests:** OAuth callback endpoint (mock OpenAI token exchange, user creation/linking)
- **Unit tests:** Agent API key resolution with OAuth priority
- **Integration tests:** Full OAuth flow with mocked OpenAI endpoints (authorize → callback → token → LLM call)
- **Frontend tests:** Login page renders both buttons, callback page handles success/error states
- **E2E:** Skip (OAuth redirect to real OpenAI not feasible in CI; test with seeded tokens)
