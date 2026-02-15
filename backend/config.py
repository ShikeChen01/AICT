import os

from pydantic import Field
from pydantic_settings import BaseSettings

# Load .env.development when ENV=development; otherwise .env (production/default)
_env = os.getenv("ENV", "").lower()
_env_file = ".env.development" if _env == "development" else ".env"


class Settings(BaseSettings):
    # Database — use DATABASE_URL directly, or build from components
    database_url: str = "postgresql+asyncpg://aict:aict@localhost:5432/aict"
    db_user: str = ""
    db_password: str = ""
    db_name: str = ""
    db_socket_path: str = ""  # e.g. /cloudsql/project:region:instance

    # Auth
    api_token: str = "change-me-in-production"
    firebase_credentials_path: str = ""
    firebase_project_id: str = ""

    # E2B
    e2b_api_key: str = ""
    e2b_base_url: str = "https://api.e2b.dev"
    e2b_timeout_seconds: int = Field(default=60, ge=5, le=600)
    e2b_template_id: str = ""

    # LLM
    claude_api_key: str = ""
    gemini_api_key: str = ""
    claude_model: str = "claude-3-5-sonnet-latest"
    gemini_model: str = "gemini-2.0-flash"
    llm_request_timeout_seconds: int = Field(default=60, ge=5, le=300)
    llm_max_tokens: int = Field(default=1024, ge=128, le=8192)
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_fallback_enabled: bool = True

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

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    auto_run_migrations_on_startup: bool = True

    model_config = {
        "env_file": _env_file,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "env_ignore_empty": True,
    }


settings = Settings()
