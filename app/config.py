from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DEPLOYMENT_TYPE: str = Field(default="debug")
    MYSQL_HOST: str = "mysql-db"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASS: str
    MYSQL_DATABASE: str = "MELEReview"
    SECRET_KEY: str = Field(min_length=32)
    ADMIN_USER: str = Field(default="admin")
    ADMIN_PASS: str = Field(default="password")
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_BYTES: int = 8 * 1024 * 1024
    MAX_MEDIA_BYTES: int = 8 * 1024 * 1024
    MEDIA_MAX_EDGE: int = 1600
    MEDIA_SWEEP_HOURS: int = 6
    MEDIA_GRACE_HOURS: int = 24
    MAX_OPEN_INVITES: int = 5
    COOKIE_SECURE: bool | None = None
    DATABASE_URL_OVERRIDE: str | None = Field(default=None, validation_alias="DATABASE_URL")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("COOKIE_SECURE", mode="before")
    @classmethod
    def blank_means_unset(cls, value: object) -> object:
        """Treat an empty value as absent.

        Compose adds `COOKIE_SECURE` with an empty interpolation default, which
        arrives as `""`. Pydantic refuses to parse that as a boolean, so the whole
        app failed at import instead of falling back to the deployment's value.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
        return self.db_url

    @property
    def DEBUG(self) -> bool:
        return self.DEPLOYMENT_TYPE.lower() in ("debug", "true", "1", "yes")

    @property
    def is_debug(self) -> bool:
        return self.DEBUG

    @property
    def secure_cookies(self) -> bool:
        if self.COOKIE_SECURE is not None:
            return self.COOKIE_SECURE
        return not self.DEBUG

    @property
    def upload_dir(self) -> Path:
        return Path(self.UPLOAD_DIR)


Config = Settings


@lru_cache
def get_config() -> Settings:
    return Settings()
