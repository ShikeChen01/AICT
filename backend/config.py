import os

from pydantic import Field
from pydantic_settings import BaseSettings

# Load .env.development when ENV=development; otherwise .env (production/default)
_env = os.getenv("ENV", "").lower()
_env_file = ".env.development" if _env == "development" else ".env"


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://aict:aict@localhost:5432/aict"
    db_ssl_mode: str = "disable"  # "disable" (local dev) | "require" (VM)

    # Project secrets encryption (Fernet). If blank, values stored unencrypted (dev only).
    secret_encryption_key: str = ""

    # Auth
    api_token: str = "change-me-in-production"
    firebase_credentials_path: str = ""
    firebase_project_id: str = ""

    # LLM
    claude_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    moonshot_api_key: str = ""
    moonshot_base_url: str = "https://api.moonshot.ai/v1"
    manager_model_default: str = "claude-sonnet-4-6"
    cto_model_default: str = "claude-opus-4-6"
    engineer_junior_model: str = "kimi-k2"
    engineer_intermediate_model: str = "claude-sonnet-4-6"
    engineer_senior_model: str = "claude-opus-4-6"
    llm_request_timeout_seconds: int = Field(default=60, ge=5, le=300)
    llm_max_tokens: int = Field(default=1024, ge=128, le=8192)
    llm_max_tokens_agent_loop: int = Field(
        default=10000,
        ge=128,
        le=65536,
        description="Max output tokens for the universal agent loop (enables large tool payloads e.g. write_architecture_doc).",
    )
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_fallback_enabled: bool = True
    llm_use_legacy_http: bool = False

    # Git
    github_token: str = ""
    github_api_base_url: str = "https://api.github.com"
    code_repo_url: str = ""
    spec_repo_path: str = "/data/specs"
    code_repo_path: str = "/data/project"
    provision_repos_on_startup: bool = True
    clone_code_repo_on_startup: bool = True

    # Agent limits
    max_engineers: int = Field(default=5, ge=1, le=5)

    # LangGraph persistence (PostgresSaver for production; MemorySaver when False)
    graph_persist_postgres: bool = Field(default=False, description="Use PostgresSaver for graph checkpoints")

    # Test login — hardcoded credentials for internal dev/testing access.
    # Safe to keep in source: no API keys or sensitive resources are accessible
    # with just email+password; the real secrets remain in env vars.
    test_login_enabled: bool = True
    test_login_email: str = "aicttest@aict.com"
    test_login_password: str = "f8a9sfa32!@#%Daf342q98v!%#@dscx90"

    # RAG / Knowledge Base (Voyage AI)
    voyage_api_key: str = ""
    voyage_model: str = "voyage-3-large"
    knowledge_chunk_size_tokens: int = Field(default=512, ge=64, le=2048)
    knowledge_chunk_overlap_tokens: int = Field(default=100, ge=0, le=512)
    knowledge_max_file_size_bytes: int = Field(default=52428800, description="50 MB per file")
    knowledge_embed_batch_size: int = Field(default=128, ge=1, le=512)

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    auto_run_migrations_on_startup: bool = True
    startup_step_timeout_seconds: int = Field(default=20, ge=1, le=300)

    # Sandbox VM — self-hosted Docker sandbox on a GCE instance (legacy)
    sandbox_vm_host: str = ""          # e.g. "34.9.162.152" (external); used when internal not set
    sandbox_vm_internal_host: str = ""  # e.g. "10.128.0.3" — use for backend→sandbox when set (VPC)
    sandbox_vm_pool_port: int = 9090
    sandbox_vm_master_token: str = ""

    # Sandbox Orchestrator (GKE) — replaces sandbox VM when set
    # When sandbox_orchestrator_host is set, the backend uses GKE orchestrator
    # instead of the legacy Docker pool manager on the sandbox VM.
    sandbox_orchestrator_host: str = ""  # e.g. "sandbox-orchestrator.sandbox-system.svc.cluster.local"
    sandbox_orchestrator_port: int = 9090
    sandbox_orchestrator_token: str = ""

    # Logging — Cloud Logging on Cloud Run (K_SERVICE) or when USE_CLOUD_LOGGING=true
    use_cloud_logging: bool = Field(
        default_factory=lambda: (
            os.getenv("K_SERVICE") is not None
            or os.getenv("USE_CLOUD_LOGGING", "").lower() in ("1", "true")
        ),
        description="Send logs to Google Cloud Logging",
    )
    log_level: str = Field(default="INFO", description="Root logger level (e.g. INFO, DEBUG)")

    model_config = {
        "env_file": _env_file,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "env_ignore_empty": True,
    }


settings = Settings()


# ── LLM Model Pricing ────────────────────────────────────────────────
#
# User-configurable pricing table used by the cost calculator.
# Keys are model name prefixes (longest match wins; exact match beats prefix).
# Values are USD price per 1,000,000 tokens for input and output respectively.
#
# Example: "claude-sonnet-4-6" matches any model whose name starts with that string.
# Update these when provider pricing changes — no code changes required elsewhere.
#
LLM_MODEL_PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-opus-4-6":         {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":       {"input":  3.00, "output": 15.00},
    "claude-haiku-4-6":        {"input":  0.80, "output":  4.00},
    "claude-opus-4-5":         {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-5":       {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":        {"input":  0.80, "output":  4.00},
    # OpenAI — GPT-5 series
    "gpt-5.4-pro":             {"input": 30.00, "output": 180.00},
    "gpt-5.4":                 {"input":  2.50, "output":  15.00},
    "gpt-5.2":                 {"input": 10.00, "output":  30.00},
    "gpt-5":                   {"input":  2.00, "output":  10.00},
    "gpt-4o":                  {"input":  2.50, "output": 10.00},
    "gpt-4o-mini":             {"input":  0.15, "output":  0.60},
    "gpt-4-turbo":             {"input": 10.00, "output": 30.00},
    "gpt-4":                   {"input": 30.00, "output": 60.00},
    # OpenAI — o-series reasoning models
    "o1":                      {"input": 15.00, "output": 60.00},
    "o1-mini":                 {"input":  3.00, "output": 12.00},
    "o1-preview":              {"input": 15.00, "output": 60.00},
    "o3":                      {"input": 10.00, "output": 40.00},
    "o3-mini":                 {"input":  1.10, "output":  4.40},
    "o3-pro":                  {"input": 20.00, "output": 80.00},
    "o4-mini":                 {"input":  1.10, "output":  4.40},
    # Google
    "gemini-2.5-pro":          {"input":  1.25, "output":  5.00},
    "gemini-2.0-flash":        {"input":  0.10, "output":  0.40},
    "gemini-2.0-flash-lite":   {"input":  0.075,"output":  0.30},
    # Moonshot / Kimi (OpenAI-compatible — api.moonshot.ai/v1)
    # kimi-k2 family (prefix match covers -turbo-preview, -0905-preview, -0711-preview variants)
    "kimi-k2-thinking":        {"input":  0.15, "output":  2.50},
    "kimi-k2-turbo":           {"input":  0.15, "output":  2.50},
    "kimi-k2":                 {"input":  0.15, "output":  2.50},
    # kimi-k2.5 multimodal
    "kimi-k2.5":               {"input":  0.15, "output":  2.50},
    # legacy moonshot-v1 models
    "moonshot-v1-8k":          {"input":  0.12, "output":  0.12},
    "moonshot-v1-32k":         {"input":  0.24, "output":  0.24},
    "moonshot-v1-128k":        {"input":  1.00, "output":  1.00},
}
