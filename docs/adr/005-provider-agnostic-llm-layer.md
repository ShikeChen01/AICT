# ADR-005: Provider-Agnostic LLM Layer

## Status

Accepted

## Context

AICT agents need LLM completions. The LLM market is volatile — new models, new providers, and new pricing appear frequently. Different agent roles benefit from different model tiers (expensive reasoning models for Manager/CTO, cheaper models for junior engineers).

Options:
1. **Direct SDK calls per provider scattered through the codebase** — fastest to implement, impossible to maintain or swap.
2. **Single provider lock-in** (e.g., Anthropic only) — simplest, but no fallback and no cost optimization.
3. **Abstraction layer with provider-agnostic contracts** — upfront cost, but enables provider swapping by changing a model string.

## Decision

**The LLM layer (`backend/llm/`) defines provider-agnostic contracts and a `ProviderRouter` that resolves the correct provider from the model name string.**

Architecture:
- **Contracts** (`contracts.py`): `LLMTool`, `LLMToolCall`, `LLMMessage`, `LLMRequest`, `LLMResponse` — provider-independent dataclasses.
- **ProviderRouter** (`router.py`): keyword matching on model name (`claude` → Anthropic, `gemini` → Google, `gpt`/`o1`/`o3` → OpenAI).
- **Providers** (`providers/`): `AnthropicSDKProvider`, `GeminiProviderAdapter`, `OpenAISDKProvider` — each translates contracts to/from the provider's native SDK.
- **Model Resolver** (`model_resolver.py`): maps `(role, tier)` → default model string from environment configuration.

The only coupling point between the rest of the codebase and LLM providers is the model name string (e.g., `"claude-opus-4-5"`).

## Consequences

**Positive:**
- Swapping providers or adding new ones requires only a new provider adapter and a keyword in the router — no changes to the inner loop, prompt system, or tools.
- Different agents can use different providers simultaneously (Manager on Claude, junior engineer on Gemini).
- Provider-specific SDK quirks are isolated in adapter classes.
- Environment-based model configuration (`MANAGER_MODEL_DEFAULT`, `ENGINEER_JUNIOR_MODEL`, etc.) enables cost tuning without code changes.

**Negative:**
- Provider-agnostic contracts must represent the lowest common denominator. Provider-specific features (e.g., Anthropic's extended thinking, OpenAI's structured outputs) require contract extensions or adapter workarounds.
- Keyword-based routing is fragile — a model named `claude-gpt-hybrid` would match the wrong provider. Acceptable because model names are controlled by configuration.
- Testing requires mocking at the contract level, not the SDK level.
