from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://aict:aict@localhost:5432/aict"

    # Auth
    api_token: str = "change-me-in-production"

    # E2B
    e2b_api_key: str = ""

    # LLM
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Git
    code_repo_url: str = ""
    spec_repo_path: str = "/data/specs"
    code_repo_path: str = "/data/project"

    # Agent limits
    max_engineers: int = 5

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
