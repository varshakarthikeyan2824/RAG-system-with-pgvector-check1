from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    database_url: str
    groq_api_key: SecretStr
    session_secret_key: SecretStr
    service_api_key: SecretStr
    ollama_embed_url: str = "http://localhost:11434/api/embed"

    app_env: Literal["development", "production", "test"] = "development"

    @model_validator(mode="after")
    def check_production_secrets(self):
        if self.app_env == "production":
            for name in ("service_api_key", "session_secret_key"):
                value = getattr(self, name).get_secret_value()
                if len(value) < 32 or value.startswith("replace-with"):
                    raise ValueError(
                        f"{name} must be a random value of at least 32 characters "
                        "in production"
                    )
        return self

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    cors_allowed_origins: str = ""

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]
        if "*" in origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must list exact origins, not '*'")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
