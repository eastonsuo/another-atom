from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Another Atom"
    environment: str = "development"
    database_url: str = "sqlite:///./data/another_atom.db"
    studio_dist: Path = Path("studio/dist")
    llm_provider: str = "mock"
    ollama_api_key: str | None = None
    ollama_host: str = "https://ollama.com"
    ollama_model: str = "deepseek-v4-pro"
    ollama_timeout_seconds: float = 120
    demo_quota_units: int = 100
    public_base_url: str = "http://localhost:8000"
    worker_poll_seconds: float = 0.5
    worker_lease_seconds: int = 600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
