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

    # Online ordering (Phase 3). No real payment provider is integrated yet (V-06): "sandbox" is a test gateway
    # that is refused when APP_ENV=production. Leave PAYMENT_GATEWAY empty to offer pay-at-pickup/delivery only.
    PAYMENT_GATEWAY: str = ""  # "", "sandbox" (development only) or "bakong"
    PAYMENT_SANDBOX_SECRET: str = ""
    # Bakong KHQR (NBC). SIT: https://sit-api-bakong.nbc.org.kh  Production: https://api-bakong.nbc.org.kh
    BAKONG_API_URL: str = "https://sit-api-bakong.nbc.org.kh"
    BAKONG_API_TOKEN: str = ""  # from the Bakong Open API site; expires after 90 days
    BAKONG_ACCOUNT_ID: str = ""  # receiving Bakong account, e.g. name@bank
    BAKONG_MERCHANT_TYPE: str = "individual"  # individual (KHQR tag 29) or merchant (tag 30)
    BAKONG_MERCHANT_ID: str = ""  # tag 30 only
    BAKONG_ACQUIRING_BANK: str = ""  # tag 30 only
    BAKONG_MERCHANT_NAME: str = ""  # shown in the payer's app, max 25 characters
    BAKONG_MERCHANT_CITY: str = "Phnom Penh"
    BAKONG_MCC: str = "5999"  # NBC examples use 5999; confirm the code your bank registers for a restaurant
    BAKONG_QR_MINUTES: int = 10
    PUBLIC_RATE_LIMIT_PER_MINUTE: int = 60

    # SMS. "plasgate" sends through PlasGate's REST API; empty means messages are only logged (and phone sign-in is unavailable).
    SMS_PROVIDER: str = ""
    PLASGATE_API_URL: str = "https://cloudapi.plasgate.com"
    PLASGATE_PRIVATE_KEY: str = ""
    PLASGATE_SECRET: str = ""
    PLASGATE_SENDER: str = ""  # sender ID agreed with PlasGate

    # GrabFood partner integration. Grab calls RMS with the client ID/secret below (we issue them to Grab in the Grab
    # developer portal); RMS calls Grab with the OAuth client Grab issues to us. Confirm the auth URL in the portal.
    GRABFOOD_PARTNER_CLIENT_ID: str = ""
    GRABFOOD_PARTNER_CLIENT_SECRET: str = ""
    GRABFOOD_CLIENT_ID: str = ""
    GRABFOOD_CLIENT_SECRET: str = ""
    GRABFOOD_API_URL: str = "https://partner-api.grab.com/grabfood"
    GRABFOOD_AUTH_URL: str = "https://partner-api.grab.com/grabid/v1/oauth2/token"

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
