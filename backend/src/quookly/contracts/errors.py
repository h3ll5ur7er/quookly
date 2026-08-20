"""Errors that cross layer boundaries.

An access service raises these rather than letting a storage-specific exception escape.
A caller should never have to catch an `IntegrityError` to learn that an email was taken.
"""


class QuooklyError(Exception):
    """Base class for errors the application raises deliberately."""


class EmailAlreadyRegistered(QuooklyError):
    """An account already exists for that email address."""
