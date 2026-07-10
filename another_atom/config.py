from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Another Atom"
    environment: str = "development"
    database_url: str = "sqlite:///./data/another_atom.db"
    studio_dist: Path = Path("studio/dist")
    llm_provider: str = "mock"
    demo_quota_units: int = 100
    public_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
