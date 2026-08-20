"""Password hashing and token issue/verification.

Security code fails silently when it fails — a token that verifies when it should not
looks exactly like one that should. These tests therefore spend most of their effort on
the rejection cases.
"""

import base64
import json
from collections.abc import Iterator
from datetime import timedelta

import pytest
from pytest import MonkeyPatch

from quookly.contracts.security import Principal
from quookly.utilities.configuration import get_settings
from quookly.utilities.security import (
    hash_password,
    issue_token,
    read_token,
    verify_password,
)

PASSWORD = "correct horse battery staple"
SIGNING_KEY = "a-test-signing-key-of-sufficient-length-0123456789"


@pytest.fixture(autouse=True)
def fixed_secret(monkeypatch: MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("QUOOKLY_SECRET_KEY", SIGNING_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def unsigned_token(claims: dict[str, object]) -> str:
    """Forge a token claiming no signature is needed — the classic JWT attack."""

    def segment(payload: dict[str, object]) -> str:
        raw = json.dumps(payload).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{segment({'alg': 'none', 'typ': 'JWT'})}.{segment(claims)}."


class TestPasswordHashing:
    def test_a_password_verifies_against_its_own_hash(self) -> None:
        assert verify_password(PASSWORD, hash_password(PASSWORD)) is True

    def test_a_wrong_password_does_not_verify(self) -> None:
        assert verify_password("not the password", hash_password(PASSWORD)) is False

    def test_hashing_is_salted(self) -> None:
        """Equal passwords must not produce equal hashes, or the store leaks who shares one."""
        assert hash_password(PASSWORD) != hash_password(PASSWORD)

    def test_the_password_is_not_recoverable_from_the_hash(self) -> None:
        assert PASSWORD not in hash_password(PASSWORD)

    def test_a_malformed_hash_is_rejected_rather_than_raising(self) -> None:
        """A corrupt row must fail the login, not crash the endpoint."""
        assert verify_password(PASSWORD, "not-a-hash") is False

    def test_an_empty_hash_is_rejected(self) -> None:
        assert verify_password(PASSWORD, "") is False


class TestTokens:
    def test_a_token_round_trips_to_its_principal(self) -> None:
        principal = read_token(issue_token(cook_id=7, is_admin=True))
        assert principal == Principal(cook_id=7, is_admin=True)

    def test_a_non_admin_stays_a_non_admin(self) -> None:
        principal = read_token(issue_token(cook_id=7, is_admin=False))
        assert principal is not None
        assert principal.is_admin is False

    def test_an_expired_token_is_rejected(self) -> None:
        token = issue_token(cook_id=7, is_admin=False, lifetime=timedelta(seconds=-1))
        assert read_token(token) is None

    def test_a_token_signed_with_another_key_is_rejected(self, monkeypatch: MonkeyPatch) -> None:
        """Tokens from another instance, or from before a key rotation, are not ours."""
        token = issue_token(cook_id=7, is_admin=False)
        monkeypatch.setenv("QUOOKLY_SECRET_KEY", "a-different-key-that-is-also-long-enough-xxxx")
        get_settings.cache_clear()
        assert read_token(token) is None

    def test_a_tampered_payload_is_rejected(self) -> None:
        token = issue_token(cook_id=7, is_admin=False)
        header, payload, signature = token.split(".")
        forged = (
            base64.urlsafe_b64encode(json.dumps({"sub": "7", "admin": True}).encode())
            .rstrip(b"=")
            .decode()
        )
        assert read_token(f"{header}.{forged}.{signature}") is None

    def test_an_unsigned_token_is_rejected(self) -> None:
        """`alg: none` must never be honoured, however well-formed the claims are."""
        assert read_token(unsigned_token({"sub": "7", "admin": True})) is None

    def test_rubbish_is_rejected(self) -> None:
        assert read_token("not-a-token") is None
        assert read_token("") is None

    def test_a_token_without_a_subject_is_rejected(self) -> None:
        """Claims we depend on must be present, not defaulted."""
        import jwt

        token = jwt.encode({"admin": True}, SIGNING_KEY, algorithm="HS256")
        assert read_token(token) is None
