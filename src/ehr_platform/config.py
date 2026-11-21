"""Application settings, read from environment variables or a local ``.env`` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="EHR_", extra="ignore")

    data_dir: Path = Path("data")

    # Any OpenAI-compatible chat completions API. The defaults target OpenAI;
    # point the base URL at another provider (for example Gemini) to use it.
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Path prefix the API is served under by a reverse proxy, e.g. "/api".
    api_root_path: str = ""

    search_top_k: int = Field(default=5, ge=1, le=50)
    search_max_query_length: int = Field(default=300, ge=1)

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "store" / "ehr.db"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"


@lru_cache
def get_settings() -> Settings:
    return Settings()
