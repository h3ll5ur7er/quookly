"""Configuration is a utility: typed settings resolved from the environment.

The security-relevant behaviour is the secret key. A hardcoded default would be a
foot-gun that ships to every self-hosted instance, so production refuses to start
without one and development generates a throwaway.
"""

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from quookly.utilities.configuration import Settings, get_settings

VALID_KEY = "a-signing-key-that-is-long-enough-to-be-safe-0123"

QUOOKLY_VARS = (
    "QUOOKLY_ENVIRONMENT",
    "QUOOKLY_SECRET_KEY",
    "QUOOKLY_DATABASE_URL",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: MonkeyPatch) -> None:
    """Settings read the process environment; tests must not inherit the developer's."""
    for name in QUOOKLY_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


class TestDefaults:
    def test_development_is_the_default_environment(self) -> None:
        assert Settings().environment == "development"

    def test_the_default_datastore_is_local_sqlite(self) -> None:
        """SQLite only at v1, and it must work with no configuration at all (ADR-009)."""
        url = Settings().database_url
        assert url.startswith("sqlite+aiosqlite://"), url


class TestEnvironmentOverrides:
    def test_settings_are_read_from_prefixed_variables(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite:///./custom.db")
        assert Settings().database_url == "sqlite+aiosqlite:///./custom.db"

    def test_the_prefix_is_required(self, monkeypatch: MonkeyPatch) -> None:
        """An unprefixed DATABASE_URL belongs to something else and must be ignored."""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./wrong.db")
        assert "wrong.db" not in Settings().database_url


class TestSecretKey:
    def test_production_refuses_to_start_without_a_secret_key(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("QUOOKLY_ENVIRONMENT", "production")
        with pytest.raises(ValidationError, match="QUOOKLY_SECRET_KEY"):
            Settings()

    def test_production_accepts_a_supplied_secret_key(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("QUOOKLY_ENVIRONMENT", "production")
        monkeypatch.setenv("QUOOKLY_SECRET_KEY", VALID_KEY)
        assert Settings().secret_key.get_secret_value() == VALID_KEY

    def test_a_short_key_is_refused(self, monkeypatch: MonkeyPatch) -> None:
        """RFC 7518: an HS256 key shorter than the hash output weakens every token."""
        monkeypatch.setenv("QUOOKLY_SECRET_KEY", "hunter2")
        with pytest.raises(ValidationError, match="at least 32 bytes"):
            Settings()

    def test_the_generated_key_satisfies_its_own_rule(self) -> None:
        generated = Settings().secret_key.get_secret_value()
        assert len(generated.encode()) >= 32

    def test_development_generates_a_key_rather_than_shipping_one(self) -> None:
        """A default key baked into the source would be the same on every instance."""
        first = Settings().secret_key.get_secret_value()
        second = Settings().secret_key.get_secret_value()
        assert first, "development must still produce a usable key"
        assert first != second, "the generated key must be ephemeral, not a constant"

    def test_the_secret_key_does_not_leak_when_rendered(self, monkeypatch: MonkeyPatch) -> None:
        """Settings end up in logs and tracebacks; the key must not travel with them."""
        secret = "do-not-print-me-and-also-long-enough-to-be-valid-01"
        monkeypatch.setenv("QUOOKLY_SECRET_KEY", secret)
        settings = Settings()
        assert secret not in repr(settings)
        assert secret not in str(settings.secret_key)


class TestAccessor:
    def test_settings_are_resolved_once(self) -> None:
        assert get_settings() is get_settings()
