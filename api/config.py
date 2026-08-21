from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DEBUG: bool = Field(default_factory=lambda: os.getenv("DEPLOYMENT_TYPE", "debug") == "debug")
    MYSQL_HOST: str = "mysql-db"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASS: str
    MYSQL_DATABASE: str = "MELEReview"
    SECRET_KEY: str = Field(min_length=32)
    CORS_ALLOW_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    # raw override via env DATABASE_URL; keep field name private to allow property alias
    DATABASE_URL_OVERRIDE: str | None = Field(default=None, validation_alias="DATABASE_URL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def db_url(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASS}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def DATABASE_URL(self) -> str:  # type: ignore[override]
        """Backwards compat alias — returns computed URL."""
        return self.db_url

    @property
    def is_debug(self) -> bool:
        return self.DEBUG


# Backwards compat alias for consumers importing Config
Config = Settings


@lru_cache
def get_config() -> Settings:
    return Settings()
