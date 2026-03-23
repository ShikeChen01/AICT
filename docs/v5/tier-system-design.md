# V5: Membership & Sandbox Billing with Stripe

## Overview

AICT is open-source infrastructure for multi-agent orchestration. We charge a small membership fee to cover our platform overhead (Cloud Run, Postgres, networking). Users bring their own LLM API keys and pay their own inference costs directly. Sandbox compute (headless + desktop VMs) is included in the membership with usage limits. We break even on infra — this isn't a margin business.

---

## Business Model

**What we charge for:** Platform overhead — keeping the backend running on GCloud.
**What users pay separately:** LLM API costs (their own keys, their own bills).
**Sandbox compute:** Included in membership tiers with hour limits. We're not marking it up.

The $20/mo Individual subscription is the revenue that keeps the lights on. Free tier exists so people can try it. Enterprise is "contact us" for companies that need custom deployments.

---

## Tier Definitions

| | Free | Individual ($20/mo) | Team ($50/mo) | Enterprise |
|---|---|---|---|---|
| **Headless sandbox hours** | 15 hrs/mo | 200 hrs/mo | 1000 hrs/mo | Custom |
| **Desktop VM hours** | 15 hrs/mo | 200 hrs/mo | 1000 hrs/mo | Custom |
| **Projects** | Unlimited | Unlimited | Unlimited | Unlimited |
| **Agents** | Unlimited | Unlimited | Unlimited | Unlimited |
| **LLM usage** | Own keys | Own keys | Own keys | Own keys |
| **Desktop VMs** | Yes | Yes | Yes | Yes |
| **Team members** | 1 | 1 | 3 | Custom |
| **VM snapshots** | No | No | No | Yes |
| **Data export/migration** | No | No | No | Yes |
| **Support** | Community | Community | Priority | Dedicated |
| **Overage** | Hard cap | Hard cap | Hard cap | Custom |

**Free tier is generous** — 15+15 hours lets people actually build something real, not just kick the tires. Hard caps everywhere — no metered overage billing. When you hit the limit, you upgrade or wait for next month. Keeps Stripe integration dead simple (flat subscriptions, no metered line items).

**Individual is very generous** — 200+200 hours covers heavy daily usage. At ~6.5 hrs/day of continuous sandbox use, that's more than most users need.

**Team = 3 seats sharing one pool.** $50/mo ÷ 3 = ~$17/seat. 1000+1000 hours is enough for a small team running agents around the clock.

**Enterprise = contact sales.** VM snapshots, data migration, custom limits, dedicated infra. Not self-serve.

---

## Prerequisite: Per-User API Key Management

Currently, LLM API keys are server-wide environment variables (`claude_api_key`, `openai_api_key`, `gemini_api_key` in `backend/config.py`). All users share the same keys — the platform operator pays for all inference. This must change before billing makes sense.

### How it works

Users enter their own LLM provider API keys in User Settings. Keys are encrypted at rest (Fernet, same as `ProjectSecrets`). The LLM router resolves keys per-request: user key → project key → server fallback.

### New: `UserAPIKey` table

```
user_api_keys
├── id: UUID (PK)
├── user_id: UUID (FK → users.id)
├── provider: VARCHAR(50) NOT NULL        # anthropic | openai | google | moonshot
├── encrypted_key: TEXT NOT NULL           # Fernet-encrypted API key
├── display_hint: VARCHAR(20)             # "sk-...abc" (last 3 chars for UI)
├── is_valid: Boolean DEFAULT true        # set false on auth errors from provider
├── created_at: DateTime
├── updated_at: DateTime
```

**Index**: `unique(user_id, provider)` — one key per provider per user.

### LLM Router change (`backend/llm/router.py`)

Current flow:
```
get_provider(model) → settings.claude_api_key → provider instance
```

New flow:
```
get_provider(model, user_id) → lookup UserAPIKey for user+provider
                              → if found & valid: use user's key
                              → else: fall back to settings.claude_api_key (server key)
                              → if no key at all: raise "API key not configured"
```

The server-wide keys remain as fallback (for the free tier trial experience and for admin/test usage). Paid users are expected to provide their own keys.

### Frontend: API Keys section in User Settings (`/settings`)

- List configured providers with masked key hints ("sk-...abc")
- Add/update key per provider (Anthropic, OpenAI, Google, Moonshot)
- "Test" button that makes a minimal API call to verify the key works
- Delete key (reverts to server fallback if available)

### API Endpoints

```
GET  /api/v1/auth/api-keys              → [{ provider, display_hint, is_valid }]
PUT  /api/v1/auth/api-keys/{provider}   → { encrypted_key } → 200
DELETE /api/v1/auth/api-keys/{provider} → 204
POST /api/v1/auth/api-keys/{provider}/test → { valid: bool, error?: string }
```

### Free tier LLM policy

Free users can use server-wide keys (if configured) with existing `ProjectSettings` daily budget caps as a safety net. This lets them try the product. Once they upgrade, they should configure their own keys for unlimited usage. The UI prompts them but doesn't force it.

---

## Data Model Changes

### New: `Subscription` table

```
subscriptions
├── id: UUID (PK)
├── user_id: UUID (FK → users.id, unique)
├── tier: VARCHAR(20) NOT NULL DEFAULT 'free'    # free | individual | team
├── status: VARCHAR(20) NOT NULL DEFAULT 'active' # active | past_due | canceled
├── stripe_customer_id: VARCHAR(255)
├── stripe_subscription_id: VARCHAR(255)          # null for free tier
├── current_period_start: DateTime
├── current_period_end: DateTime
├── cancel_at_period_end: Boolean DEFAULT false
├── created_at: DateTime
├── updated_at: DateTime
```

### New: `UsagePeriod` table

One row per user per billing cycle. Simple counters.

```
usage_periods
├── id: UUID (PK)
├── user_id: UUID (FK → users.id)
├── period_start: Date
├── period_end: Date
├── headless_seconds: BigInteger DEFAULT 0
├── desktop_seconds: BigInteger DEFAULT 0
├── created_at: DateTime
├── updated_at: DateTime
```

**Index**: `unique(user_id, period_start)`

### Modified: `User` model

```python
tier: String(20), default="free"
stripe_customer_id: String(255), nullable
```

### Modified: `SandboxUsageEvent`

Ensure `unit_type` field exists to distinguish headless vs desktop:

```python
unit_type: String(20)   # "headless" | "desktop"
```

### New: `UserAPIKey` table (see Prerequisite section above)

No changes to `ProjectSettings` — LLM budgets are the user's own safety caps.

---

## Stripe Integration

### Products & Prices

```
Product: "AICT Individual" → Price: $20/month recurring
Product: "AICT Team"       → Price: $50/month recurring
```

That's it. No metered prices, no overage items. Flat subscriptions only.

### Config (`backend/config.py`)

```python
stripe_secret_key: str = ""
stripe_publishable_key: str = ""
stripe_webhook_secret: str = ""
stripe_individual_price_id: str = ""
stripe_team_price_id: str = ""
```

### Flow: Upgrade

```
Frontend                    Backend                         Stripe
   │                           │                              │
   ├─ POST /api/v1/billing/    │                              │
   │  checkout-session         │                              │
   │  {tier: "individual"}     │                              │
   │                           ├─ Create Stripe Customer      │
   │                           │  (if not exists)             │
   │                           ├─ stripe.checkout.Session     │
   │                           │  .create(                    │
   │                           │    customer: cus_xxx,        │
   │                           │    price: price_xxx,         │
   │                           │    mode: "subscription"      │
   │                           │  )                           │
   │  ◄── {checkout_url}       │                              │
   ├─ redirect to Stripe       │                              │
   │                           │                              │
   │                           │   webhook: checkout.complete │
   │                           ├─ update Subscription + User  │
   │                           ├─ create UsagePeriod          │
```

### Flow: Manage / Cancel

Stripe Customer Portal. One redirect.

### Flow: Cancellation

Webhook `customer.subscription.deleted`:
- Set `User.tier = "free"`
- Active sessions finish naturally
- Next sandbox start checks against free limits

### Webhook Events

| Event | Action |
|---|---|
| `checkout.session.completed` | Set tier, create Subscription + UsagePeriod |
| `customer.subscription.updated` | Sync tier, period dates |
| `customer.subscription.deleted` | Set tier to free |
| `invoice.payment_failed` | Set status to `past_due`, pause sandbox access |
| `invoice.paid` | Clear `past_due` |

---

## Backend Enforcement

### `TierService` (`backend/services/tier_service.py`)

```python
TIER_LIMITS = {
    "free": {
        "headless_seconds": 15 * 3600,
        "desktop_seconds": 15 * 3600,
        "max_team_members": 1,
        "snapshots": False,
    },
    "individual": {
        "headless_seconds": 200 * 3600,
        "desktop_seconds": 200 * 3600,
        "max_team_members": 1,
        "snapshots": False,
    },
    "team": {
        "headless_seconds": 1000 * 3600,
        "desktop_seconds": 1000 * 3600,
        "max_team_members": 3,
        "snapshots": False,
    },
}
```

**Methods:**

```python
async def check_can_start_sandbox(user, unit_type) -> None
    """Raises TierLimitError if monthly hours exhausted or past_due."""

async def get_remaining_seconds(user, unit_type) -> int
    """Seconds left in current period for this sandbox type."""

async def record_usage(user, unit_type, seconds) -> None
    """Increment UsagePeriod counters."""

async def check_can_invite_member(user, current_count) -> None
    """Raises TierLimitError if at team member cap."""

async def get_usage_summary(user) -> dict
    """Current period: used/total for headless + desktop."""
```

### Enforcement Points

| Action | Where | Check |
|---|---|---|
| Start any sandbox | `sandbox_service.py` | `check_can_start_sandbox` |
| Sandbox session end | `budget_service.py` | `record_usage` |
| Invite member | `api/v1/members.py` | `check_can_invite_member` |
| Past due payment | `sandbox_service.py` | Block new sandbox starts |

**Not enforced:** projects, agents, LLM calls, prompts, model config — all unlimited, all tiers.

### Error Response

```json
{
  "error": "tier_limit",
  "message": "You've used 15 of 15 free headless hours this month. Upgrade to Individual for 200 hours.",
  "current_tier": "free",
  "upgrade_url": "/settings/billing"
}
```

---

## API Endpoints

### `backend/api/v1/billing.py`

```
POST /api/v1/billing/checkout-session    { tier }     → { checkout_url }
POST /api/v1/billing/portal-session                   → { portal_url }
GET  /api/v1/billing/subscription                     → { tier, status, period_end, ... }
GET  /api/v1/billing/usage                            → { headless used/total, desktop used/total }
POST /api/v1/billing/webhook             (Stripe sig) → 200
```

---

## Frontend Changes

### Billing Page (`/settings/billing`)

- Current plan badge
- Usage bars: headless X/Y hrs, desktop X/Y hrs
- "Upgrade" → Stripe Checkout
- "Manage" → Stripe Portal

### Sandbox page

- Remaining hours shown next to create buttons
- Warning at 80% usage
- Hard block with upgrade prompt at 100%

### Nav

- Tier badge next to avatar

---

## Migration

### Database migration

1. Create `user_api_keys` table
2. Create `subscriptions` table
3. Create `usage_periods` table
4. Add `tier`, `stripe_customer_id` to `users`
5. Add `unit_type` to `sandbox_usage_events` if missing

### Stripe setup

1. Create 2 Products + 2 Prices in Stripe Dashboard
2. Configure Customer Portal
3. Register webhook URL
4. Set 5 env vars

### Rollout

1. Deploy with `tier_enforcement_enabled = False`
2. Deploy billing UI
3. Verify webhooks
4. Enable enforcement — existing users start as Free
5. Announce 30-day grace for existing active users

---

## File Inventory

### New
```
backend/db/models.py: UserAPIKey             # Per-user encrypted LLM API keys
backend/api/v1/api_keys.py               # CRUD + test endpoints for user API keys
backend/schemas/api_keys.py              # Request/response schemas
backend/api/v1/billing.py               # Checkout, portal, webhook, usage endpoints
backend/services/tier_service.py         # TIER_LIMITS, enforcement checks, usage recording
backend/services/stripe_service.py       # Stripe API wrapper
backend/schemas/billing.py              # Billing request/response schemas
backend/migrations/versions/xxx_add_billing.py
frontend/src/pages/BillingPage.tsx
frontend/src/components/UpgradeBanner.tsx
frontend/src/components/TierBadge.tsx
frontend/src/components/UsageGauge.tsx
frontend/src/components/APIKeyManager.tsx  # Provider key entry UI
frontend/src/hooks/useBilling.ts
```

### Modified
```
backend/config.py                       # Stripe env vars + tier_enforcement_enabled
backend/db/models.py                    # Subscription, UsagePeriod, UserAPIKey, User.tier
backend/llm/router.py                  # Look up user API key before server fallback
backend/main.py                         # Register billing + api_keys routers
backend/services/sandbox_service.py     # Tier checks before sandbox start
backend/services/budget_service.py      # Record usage on session end
backend/requirements.txt                # stripe>=11.0.0,<13.0.0
frontend/src/App.tsx                    # Billing route
frontend/src/api/client.ts             # Billing + API key management methods
frontend/src/pages/UserSettings.tsx     # API key management section
frontend/src/components/AppShell.tsx    # Tier badge
frontend/src/pages/SandboxPage.tsx      # Usage display + upgrade prompts
```

---

## Design Decisions

**Why no overage billing?**
Hard caps + flat subscriptions = dead simple Stripe integration. No metered prices, no usage record syncing, no surprise bills. User hits limit → upgrade or wait. Keeps the codebase small and the billing predictable.

**Why not limit projects/agents/LLM?**
We don't pay for those. Users bring their own API keys. Artificial limits on things that don't cost us anything is just annoying. Charge for what costs money (sandbox VMs, platform infra).

**Why is the free tier so generous?**
15 hours each of headless and desktop is enough to actually build something, not just poke around. If people can't do real work on free, they'll never see enough value to pay $20/mo.

**Why no Enterprise self-serve?**
Enterprise users want custom infra, SLAs, and invoicing. That's a conversation, not a checkout page.

**Why open-source friendly?**
The codebase will be open-sourced. The tier system is just the hosted offering's cost-recovery mechanism. Self-hosters run their own infra and skip all of this.
