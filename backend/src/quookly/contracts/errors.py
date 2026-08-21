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


class PortionsUnknown(QuooklyError):
    """The recipe's yield does not say how much of it one person eats.

    "Makes 12 pancakes" is a count of pancakes, not of people. Raised rather than guessing
    a pieces-per-serving figure, which would misportion every meal planned from it and
    give no sign that it had.
    """


class UnknownUnit(QuooklyError):
    """No such unit. Guessing one would misweigh whatever was measured with it."""


class IngredientNotRegistered(QuooklyError):
    """A recipe line points at an ingredient that is not in the registry (FR-9)."""


class UnsupportedDocument(QuooklyError):
    """The document is not one this version can read.

    Reading a format we do not understand would silently drop whatever is new in it, so
    an unrecognised version is refused rather than partially honoured.
    """


class InferenceNotConfigured(QuooklyError):
    """This instance has not been pointed at a model (FR-8, UC-8.2).

    Distinct from unavailability: nothing is wrong, nobody has said where to ask. An
    operator can act on that; "the request failed" tells them to check a network.
    """


class InferenceUnavailable(QuooklyError):
    """The model could not be reached, or failed while answering.

    A model that is switched off is a normal outcome for a self-hosted instance, not a
    crash — which is why it is an error the layers above are expected to catch.
    """


class InferenceRefused(QuooklyError):
    """The provider declined: a rejected credential, a quota, a blocked account.

    Kept apart from unavailability because the remedy is different and only the operator
    has it. "Your key is wrong" is actionable; "it failed" is not.
    """


class StructuredOutputUnusable(QuooklyError):
    """The model did not return the shape it was asked for.

    Refused rather than repaired. A half-read answer is a recipe missing ingredients, and
    guessing at what a model meant is exactly the failure FR-9 exists to prevent.
    """


class AddressNotAllowed(QuooklyError):
    """This instance will not fetch that address.

    A URL is user input and the fetch happens on the server's network. Without this an
    instance is a way to read whatever it can reach and nobody else can — its own admin
    API, a router, a cloud metadata endpoint.
    """


class ContentUnreachable(QuooklyError):
    """The page could not be fetched: no such host, no answer, or an error status."""


class ContentRefused(QuooklyError):
    """The site declined to serve the page to an automated reader.

    Large recipe sites sit behind bot protection and answer 403 to anything that is not a
    browser. Kept apart from unreachability because the remedy is different and the cook
    has it: the page works in their browser, and the words can be brought across by hand.
    """


class ContentUnreadable(QuooklyError):
    """The page was fetched and there is nothing in it worth reading.

    A PDF, a video, an empty shell rendered entirely by script, or a page so large that
    reading it is itself the problem. Reported rather than passed on: handing an empty
    page to a model produces an invented recipe.
    """
