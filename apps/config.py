from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    DEBUG: bool
    MYSQL_HOST: str
    MYSQL_PORT: str
    MYSQL_USER: str
    MYSQL_PASS: str
    MYSQL_DATABASE: str
    ACCESS_PASSWORD: str
    SECRET_KEY: str

    @property
    def DATABASE_URL(self) -> str:
        if os.environ.get("DATABASE_URL"):
            return os.environ["DATABASE_URL"]
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASS}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASS}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )


def get_config() -> Config:
    return Config(
        DEBUG=os.environ.get("DEPLOYMENT_TYPE", "debug") == "debug",
        MYSQL_HOST=os.environ.get("MYSQL_HOST", "mysql-db"),
        MYSQL_PORT=os.environ.get("MYSQL_PORT", "3306"),
        MYSQL_USER=os.environ.get("MYSQL_USER", "root"),
        MYSQL_PASS=os.environ["MYSQL_PASS"],
        MYSQL_DATABASE=os.environ.get("MYSQL_DATABASE", "MELEReview"),
        ACCESS_PASSWORD=os.environ["ACCESS_PASSWORD"],
        SECRET_KEY=os.environ["SECRET_KEY"],
    )
