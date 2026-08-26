"""Errors that cross layer boundaries.

An access service raises these rather than letting a storage-specific exception escape.
A caller should never have to catch an `IntegrityError` to learn that an email was taken.
"""


class QuooklyError(Exception):
    """Base class for errors the application raises deliberately."""


class EmailAlreadyRegistered(QuooklyError):
    """An account already exists for that email address."""


class NotYetApproved(QuooklyError):
    """The credentials were right, but nobody has let this account in yet (UC-10.6).

    Told plainly rather than folded into `InvalidCredentials`, and the distinction is safe
    precisely because it is only reachable **after** the password has matched. Somebody
    who knows the password already knows the account exists; what they do not know is that
    they are waiting on a person rather than mistyping.
    """


class Refused(QuooklyError):
    """The credentials were right, and an administrator declined this account.

    A separate sentence from `NotYetApproved` for the same reason that exists at all: "we
    have not looked yet" and "we looked and said no" are different facts, and telling
    somebody the first when the second is true leaves them waiting forever.
    """


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


class NameAlreadyMeans(QuooklyError):
    """The spelling is already this locale's name for a different registry entry.

    A name means one thing per language — the unique index on `(locale, normalised)` says
    so — or a recipe naming it could not be resolved to one ingredient. Reported rather
    than swallowed, because two entries wanting the same name in the same language are
    very often one ingredient that an import split in two.
    """

    def __init__(self, spelling: str, slug: str) -> None:
        super().__init__(f"{spelling!r} already means {slug!r} here")
        self.spelling = spelling
        self.slug = slug


class NothingToMerge(QuooklyError):
    """An entry was asked to be merged into itself."""


class PageNotWritten(QuooklyError):
    """No Academy page answers to that slug."""


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


class NotARecipe(QuooklyError):
    """The page was read and there is no recipe in it.

    Reported rather than half-answered. A recipe with no ingredients, or no name, looks
    complete on a screen and is not — which is the failure FR-9 exists to prevent.
    """


class YieldUnknown(QuooklyError):
    """The page does not say how much the recipe makes.

    Refused rather than guessed. A yield is the denominator of every quantity in a recipe,
    so an invented one misscales all of them at once — and does it silently, which is the
    kind of wrong a cook cannot see.
    """


class UnsuitableForTheTable(QuooklyError):
    """A recipe was written for people who cannot eat it (UC-1.4, UC-1.5).

    Only generation raises this. An *imported* recipe exists in the world whatever it
    contains, and hiding it would be the interface deciding something about an allergy on
    a cook's behalf (ADR-010) — but a generated one was asked for on these people's behalf,
    so producing something they cannot eat is a failure of the request rather than a fact
    about a recipe.

    Carries the verdict, because "no" without a reason is not an answer.
    """

    def __init__(self, verdict: object) -> None:
        super().__init__("the recipe that came back is not suitable for this household")
        self.verdict = verdict
