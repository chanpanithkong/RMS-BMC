from functools import lru_cache
from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Restaurant Management System"
    APP_ENV: str = "development"
    DEBUG: bool = False

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_NAME: str = "restaurant_management_db"
    DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "rms_refresh"
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    LOCKOUT_MAX_ATTEMPTS: int = 5
    LOCKOUT_WINDOW_MINUTES: int = 15
    LOCKOUT_DURATION_MINUTES: int = 15
    APPROVAL_TOKEN_MINUTES: int = 2

    FRONTEND_URL: str = "http://localhost:3000"
    REDIS_URL: str = ""
    DEFAULT_TIMEZONE: str = "Asia/Phnom_Penh"

    @model_validator(mode="after")
    def _resolve(self) -> "Settings":
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+psycopg://{self.DB_USER}:{quote(self.DB_PASSWORD, safe='')}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        elif "${DB_PASSWORD}" in self.DATABASE_URL:
            self.DATABASE_URL = self.DATABASE_URL.replace("${DB_PASSWORD}", quote(self.DB_PASSWORD, safe=""))
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY.startswith("GENERATE"):
            raise ValueError("JWT_SECRET_KEY must be set to a random secret (see .env.example)")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.FRONTEND_URL.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
