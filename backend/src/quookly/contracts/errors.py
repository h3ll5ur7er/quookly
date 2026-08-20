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


class IncompatibleUnits(QuooklyError):
    """The two units measure different kinds of thing, and no density bridges them."""


class DensityRequired(QuooklyError):
    """Converting between mass and volume needs the ingredient's density.

    Raised rather than assuming water: a wrong assumption here silently misweighs every
    dry ingredient, and flour is roughly half the density of water.
    """


class IngredientAlreadyRegistered(QuooklyError):
    """That slug is already in the registry."""


class UnknownUnit(QuooklyError):
    """No such unit. Guessing one would misweigh whatever was measured with it."""


class IngredientNotRegistered(QuooklyError):
    """A recipe line points at an ingredient that is not in the registry (FR-9)."""
