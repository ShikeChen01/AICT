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

    # E2B
    e2b_api_key: str = ""
    e2b_base_url: str = "https://api.e2b.dev"
    e2b_timeout_seconds: int = Field(default=60, ge=5, le=600)
    e2b_template_id: str = ""

    # LLM
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Git
    code_repo_url: str = ""
    spec_repo_path: str = "/data/specs"
    code_repo_path: str = "/data/project"

    # Agent limits
    max_engineers: int = Field(default=5, ge=1, le=5)

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    model_config = {"env_file": _env_file, "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
