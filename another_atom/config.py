from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Another Atom"
    environment: str = "development"
    log_level: str = "INFO"
    log_directory: Path = Path("data")
    database_url: str = "sqlite:///./data/another_atom.db"
    studio_dist: Path = Path("studio/dist")
    llm_provider: str = "mock"
    ollama_api_key: str | None = None
    ollama_host: str = "https://ollama.com"
    ollama_model: str = "deepseek-v4-pro"
    ollama_timeout_seconds: float = 300
    ollama_lead_timeout_seconds: float = 60
    ollama_failover_timeout_seconds: float = 30
    deepseek_api_key: str | None = None
    deepseek_host: str = "https://api.deepseek.com"
    demo_quota_units: int = 100
    public_base_url: str = "http://localhost:8000"
    worker_poll_seconds: float = 0.5
    worker_lease_seconds: int = 600
    session_cookie_name: str = "another_atom_session"
    session_ttl_hours: int = 168
    session_cookie_secure: bool = False
    admin_username: str = "admin"
    admin_password: str = "admin12345"
    admin_display_name: str = "Another Atom Admin"
    project_repository_root: Path = Path("data/project-repositories")
    max_source_chars: int = 120_000
    sandbox_host_url: str | None = None
    sandbox_shared_secret: str | None = None
    sandbox_image: str = "another-atom-vim-sandbox:latest"
    sandbox_worktree_root: Path = Path("data/sandbox-worktrees")
    sandbox_session_minutes: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
