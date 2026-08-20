"""Typed instance settings, resolved from the environment.

Every setting is read from a `QUOOKLY_`-prefixed environment variable so that a
self-hosted instance is configured without editing anything inside the image.
"""

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "production"]

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./quookly.db"

# RFC 7518 section 3.2: an HMAC key for HS256 should be at least as long as the hash
# output. A shorter key weakens every token signed with it.
MINIMUM_SECRET_KEY_BYTES = 32


class Settings(BaseSettings):
    """Instance configuration.

    Settings are deliberately added as they are used rather than in anticipation, so
    this grows with the phases rather than describing a system that does not exist.
    """

    model_config = SettingsConfigDict(env_prefix="QUOOKLY_", extra="ignore")

    environment: Environment = "development"
    database_url: str = DEFAULT_DATABASE_URL
    secret_key: SecretStr = SecretStr("")
    token_lifetime_hours: int = 12
    log_level: str = "INFO"

    @model_validator(mode="after")
    def resolve_secret_key(self) -> "Settings":
        """Require a secret in production; generate a throwaway in development.

        Shipping a default would give every self-hosted instance the same signing key,
        which is worse than refusing to start. Development instead gets a per-process
        key: tokens do not survive a restart, which is the correct trade for not having
        a constant in the source.
        """
        supplied = self.secret_key.get_secret_value()
        if supplied:
            if len(supplied.encode()) < MINIMUM_SECRET_KEY_BYTES:
                raise ValueError(
                    f"QUOOKLY_SECRET_KEY must be at least {MINIMUM_SECRET_KEY_BYTES} bytes. "
                    "Generate one with: "
                    'python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
                )
            return self
        if self.environment == "production":
            raise ValueError(
                "QUOOKLY_SECRET_KEY must be set when QUOOKLY_ENVIRONMENT is 'production'."
            )
        self.secret_key = SecretStr(secrets.token_urlsafe(MINIMUM_SECRET_KEY_BYTES))
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Resolve settings once per process."""
    return Settings()
