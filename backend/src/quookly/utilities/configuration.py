"""Typed instance settings, resolved from the environment.

Every setting is read from a `QUOOKLY_`-prefixed environment variable so that a
self-hosted instance is configured without editing anything inside the image.
"""

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from quookly.contracts.nutrition import NutritionSource

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

    # Which model answers, and how it is reached (V3, FR-8, UC-8.2). Configuration rather
    # than code: the same build serves a local vLLM and a hosted provider, and nothing
    # above the access layer knows which one answered.
    #
    # Empty means no provider. An instance without one still works — it simply cannot be
    # asked to interpret a page, and says so rather than failing as if something broke.
    #: Which food composition tables to believe, best first.
    #:
    #: Composition data is a measurement of a particular food supply, not a fact about an
    #: ingredient: Swiss flour is unfortified and American flour is fortified with folic
    #: acid and iron by law. So the order is an instance's own — a kitchen in Bern and one
    #: in Toronto want different answers to the same question — and it ships preferring the
    #: tables measured nearest the cooks this product was built for (ADR-045).
    #:
    #: A source left out of the list is a source this instance will not use, even if its
    #: figures are stored.
    nutrition_sources: str = "swiss,ciqual,cofid,usda"

    inference_base_url: str = ""
    inference_model: str = ""
    inference_api_key: SecretStr = SecretStr("")
    # Local models on modest hardware are slow, and a recipe page is a long prompt. The
    # default is patient rather than snappy; a self-hoster on a slower box raises it.
    inference_timeout_seconds: float = 180.0

    # Fetching a page a cook pasted a link to (UC-1.3). The URL is user input and the
    # fetch runs on the server's network, so private addresses are refused by default.
    # A self-hoster with a recipe box on their LAN turns this on deliberately.
    allow_private_fetch: bool = False
    fetch_timeout_seconds: float = 20.0

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


def preferred_sources() -> list[NutritionSource]:
    """The composition tables this instance believes, best first (ADR-045).

    A name nobody recognises is skipped rather than fatal: a typo in a setting should cost
    an instance one table, not its ability to start.
    """
    named = [word.strip().lower() for word in get_settings().nutrition_sources.split(",")]
    ordered = []
    for name in named:
        try:
            source = NutritionSource(name)
        except ValueError:
            continue
        if source not in ordered:
            ordered.append(source)
    return ordered
