"""Errors that cross layer boundaries.

An access service raises these rather than letting a storage-specific exception escape.
A caller should never have to catch an `IntegrityError` to learn that an email was taken.
"""


class QuooklyError(Exception):
    """Base class for errors the application raises deliberately."""


class EmailAlreadyRegistered(QuooklyError):
    """An account already exists for that email address."""


class InvalidCredentials(QuooklyError):
    """The email and password did not identify an account.

    Deliberately one error for both "no such account" and "wrong password". Separate
    errors would let anyone discover which addresses hold accounts.
    """


class BootstrapClosed(QuooklyError):
    """The instance already has an account, so the first-admin path is closed."""
