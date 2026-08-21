# Decisions

Architecture decision records. Each states the decision, why it was taken, and what it costs.
Superseding a decision means adding a record, not editing one.

Status values: **Accepted**, **Proposed** (awaiting confirmation), **Open** (unresolved).

---

## ADR-001 Decompose by volatility, not by feature

**Status:** Accepted

**Context.** The root `README.md` lists roughly twenty features. The obvious decomposition assigns
a service to each.

**Decision.** Decompose by volatility per the iDesign Method. See
[Volatility analysis](03-volatility-analysis.md).

**Rationale.** Five separate concerns — measurement, suitability, inference access, nutrition, and
scoring — cut across most of the feature list. Under a feature decomposition each would be
implemented several times and would have to be changed in several places at once.

**Cost.** The code will not map one-to-one onto the feature list, which makes it harder for a new
contributor to guess where something lives. Mitigated by these documents and by the naming
convention: a service's name states its volatility.

---

## ADR-002 Four managers, not one per entity

**Status:** Accepted — amended, five as of cooking mode (see below). The title records the decision
as originally taken; the test it encodes is unchanged.

**Context.** Candidate managers presented themselves for user, recipe, plan, stock, shopping list,
social, gamification, academy, AI, and search.

**Decision.** Four: `RecipeManager`, `PlanningManager`, `PantryManager`, `EngagementManager`.

**Rationale.** A manager encapsulates the volatility of a *use case sequence*. Ten managers would
require manager-to-manager calls, which the call rules forbid, and would mean each new feature adds
a manager — the definition of a decomposition that does not converge.

**Cost.** Each manager is larger. `RecipeManager` in particular carries acquisition, presentation,
and discovery. If any of these begins to change for reasons of its own, it should be split out —
and that is a signal to watch for, not a failure.

**Amended:** a fifth manager, `CookingManager`, was added when cooking mode entered scope. It was
admitted because it passes the test this record exists to enforce, on all three counts: it
encapsulates a volatility nothing else covers (V15 execution guidance), it owns genuine workflow
state that no other manager holds (a live, device-spanning session), and it changes for its own
reasons — refined against people cooking dinner, not against recipe sources or stock accounting.

Adding a manager is not a violation of this ADR. Adding one *per entity or per feature* is. The
count is not the rule; the test is.

**Amended again:** this record also asserted that account management needed no manager. Building it
refuted that — see [ADR-021](#adr-021-account-management-does-need-a-manager).

---

## ADR-003 Inference is a resource, prompting is an activity

**Status:** Accepted

**Context.** Quookly must support Ollama, vLLM, and hosted providers with user-supplied keys.

**Decision.** `ModelAccess` encapsulates *reaching a model*. `GenerationEngine` and
`InterpretationEngine` encapsulate *what to ask and how to read the answer*. No service above the
access layer names a provider.

**Rationale.** These change at different rates for different reasons: prompt strategy is iterated
constantly, provider plumbing changes when someone switches backends. A single `AIManager` would be
named after a technology rather than a volatility and would accumulate both.

**Cost.** An extra interface between the engine and the provider SDK, and a lowest-common-
denominator interface — capabilities such as tool-calling need explicit modelling rather than
direct use.

---

## ADR-004 Plans reserve stock; cooking consumes it

**Status:** Accepted

**Context.** The brain-dump says "automatic stock deduction when planning meals". Read literally,
planning a meal removes ingredients from the pantry.

**Decision.** Planning creates a **reservation**. Cooking converts the reservation into
**consumption**. Cancelling a plan releases the reservation.

**Rationale.** Literal deduction makes the pantry lie: the butter is still in the fridge. Two plans
could each believe they have it, cancelling a plan would need stock to be re-added, and the shopping
list would be computed against a pantry that does not exist. Reservation keeps stock truthful while
still preventing double-allocation, and the shopping list falls out of the reservation shortfall.

**Cost.** More state: stock has free and reserved quantities, and reservations need lifecycle
handling for abandoned plans.

**Confirmed.** The deciding case is the ordinary one: a cook plans a dish, changes their mind, and
cooks something else. A reservation is released and the ingredients are simply still there. Literal
deduction would have to *re-add* stock that never left the fridge, and any bug in that path shows up
as food the system believes was eaten.

This makes **release** a first-class operation, not an error path. Three things release a
reservation: cancelling a plan, reassigning a slot to a different recipe, and abandoning a cooking
session (UC-9.8, FR-19). Each must be as well tested as consumption — the failure mode of a missed
release is stock that is invisible forever, which is precisely the waste the product exists to
reduce.

---

## ADR-005 Eaters are not user accounts

**Status:** Accepted

**Context.** Dietary constraints must be recorded for household members and regular guests.

**Decision.** An `Eater` is a first-class concept with constraints and an age band, owned by a Cook,
with no login. A Cook is associated with their own Eater record.

**Rationale.** Most people cooked for will never use the software. Requiring an account to record a
guest's shellfish allergy would make the feature unusable.

**Cost.** Two concepts where systems usually have one, and a future "guest claims their profile"
feature would need a merge path.

---

## ADR-006 Allergen determination is structural

**Status:** Accepted — safety-critical

**Context.** Models generate recipes and will happily assert dietary properties about them.

**Decision.** Suitability and allergen conclusions are computed by `SuitabilityEngine` from resolved
structured ingredients and their registry allergen classifications. Claims appearing in generated
text are discarded. `SuitabilityEngine` is a pure function with no I/O and no model access.

**Rationale.** A model asserting "nut-free" about a recipe containing marzipan is a health incident.
Structural determination is verifiable, testable, and explainable — it can state *which* ingredient
caused a verdict. The separation is architectural rather than procedural so that it cannot be
bypassed under deadline.

**Built.** `SuitabilityEngine` is a pure function of resolved ingredients and structured
constraints, and its test file is a table of cases with no fixtures, no database and no model — the
standard a safety-critical component has to meet in order to be argued about.

Three behaviours carry the decision:

- **Unknown outranks suitable.** An ingredient nobody has classified makes the answer *unknown*, not
  safe. Silence about a nut is not an absence of nuts, and "classified as containing nothing" is a
  different fact from "never looked at" — which is why the engine is told which of the two it has.
- **A known violation outranks a doubt.** There is nothing left to find out about it.
- **The verdict names the eater and the ingredient responsible.** A refusal a cook cannot act on is
  barely better than no answer.

The purity is enforced, not merely intended: the `import-linter` contract added in Phase 1 forbids
every engine from reaching resource access, so this engine cannot acquire a database call or a model
call without breaking the build. A test also asserts the module's own source contains no I/O.

**Cost.** Every ingredient must resolve to a registry entry before suitability can be judged; an
unresolved ingredient must be treated as *unknown*, not as *safe*. Unknown must surface as a warning
in the UI, never be silently omitted.

---

## ADR-007 Nutrition data: USDA FoodData Central as the base

**Status:** Accepted

**Context.** Nutrition requires reference data. The constraint set is: usable freely, redistributable
inside a self-hosted container, and with no licensing obligation that could become a problem for
anyone running an instance.

**Decision.** Ship **USDA FoodData Central** as the base dataset. Where a clearly-licensed regional
dataset improves accuracy for a target locale, add it as an overlay. Do not vendor any dataset whose
terms are ambiguous.

**Verified licensing** (checked August 2026 against the publishers' own pages, not summaries):

| Dataset | Licence | Obligation | Verdict |
| --- | --- | --- | --- |
| [USDA FoodData Central](https://fdc.nal.usda.gov/) | CC0 1.0, public domain | None. Attribution requested, not required | **Base dataset** |
| [UK CoFID](https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid) | Open Government Licence v3.0 | Attribution | Optional overlay for `en_GB` |
| [Ciqual (ANSES)](https://www.anses.fr/en/content/ciqual-nutritional-composition-table) | Licence Ouverte (Etalab) | Attribution | Optional overlay for `fr_CH` |
| [Open Food Facts](https://world.openfoodfacts.org/terms-of-use) | ODbL | Attribution **and share-alike** | Rejected |
| [Swiss Food Composition Database](https://opendata.swiss/en/dataset/naehrwerte_lebensmittel) | opendata.swiss "Open use. Must provide the source." | Attribution | Overlay for `de_CH` and `fr_CH` |

**Rationale.** CC0 is the only status with genuinely zero obligations: no attribution requirement, no
share-alike, no restriction on redistribution inside an image. Every self-hoster inherits those
terms, and "it should just work" for them too, without any of them having to read a licence.

USDA is a US dataset while the target locales are British and Swiss. That matters less than it
appears: nutrient values for generic ingredients — flour, butter, chicken thigh — travel well across
borders. What does *not* travel is naming and shelf products, and that is V14 localisation, already
handled separately by locale-specific ingredient names.

**Why Open Food Facts is rejected.** ODbL's share-alike applies to *adapted databases*: publish one
and it must be offered under ODbL. Shipping a seeded ingredient registry derived from Open Food Facts
would plausibly trigger that. The obligation is survivable but it is an obligation, and it would be
inherited by everyone running an instance. It is also the wrong shape — barcode-level packaged
products rather than the generic ingredients recipes are written from.

**On the Swiss database.** An earlier revision of this record excluded it as ambiguous. That was
wrong, and the correction matters because two of the three target locales are Swiss.

The apparent conflict was between the FSVO's generic federal-website copyright boilerplate — *"written
permission must be obtained in advance from the copyright holder before any material is reproduced"* —
and the dataset's own download page. The boilerplate governs website content generally; the dataset
carries its own published terms, and those govern.

Those terms are explicit on two independent pages:

- The [download page](https://naehrwertdaten.ch/en/downloads/) states the data *"may also be used for
  commercial purposes (e.g. integration into food composition calculation software or nutrition diary
  app) and scientific purposes, subject to acknowledgment of the source"* — naming almost exactly this
  application.
- The dataset's record on the federal open data portal declares its terms as
  [**"Open use. Must provide the source."**](https://opendata.swiss/en/terms-of-use), which in the
  opendata.swiss taxonomy means non-commercial use permitted, **commercial use permitted**, and
  attribution mandatory.

That is a permissive open-data grant, and it makes the Swiss database the preferred overlay for
`de_CH` and `fr_CH`. Attribution is *mandatory* rather than requested here, which is why FR-20 exists
and why the attribution surface is a requirement rather than a courtesy.

**Consequences for the design.**

- Every nutrient profile records its **source and licence** alongside its values and confidence
  (FR-20). This is what makes attribution possible per record rather than per application, and it is
  what allows an OGL or Licence Ouverte overlay to carry its own required credit.
- Because the source sits behind `IngredientAccess` and `NutritionEngine` consumes whatever it is
  handed, swapping or layering datasets is a data change, not a code change (V6, V13).
- Attribution for USDA is not legally required, but Quookly credits it anyway. It costs a line and
  the request is reasonable.

**Why USDA remains the base rather than the Swiss set.** Coverage. FoodData Central carries orders of
magnitude more entries and answers for any locale, including ones Quookly does not target yet. The
Swiss and UK sets are better *where they apply*, which is what an overlay is for: match on the
locale, fall back to the base.

**Cost.** Overlays carry mandatory attribution, so the source and licence of every profile must be
tracked and displayed (FR-20) rather than the whole application carrying one blanket credit. That is
a small amount of plumbing, and it is the price of using data that is better for the locales this
product actually targets.

## ADR-008 Enforce the call rules with import-linter

**Status:** Accepted

**Context.** The call rules are currently prose. Prose is not enforcement, and layering rules decay
under deadline pressure.

**Decision.** Add `import-linter` to the backend with a layered contract, and run it as part of
`just backend check`.

**Rationale.** NFR-10 requires conformance to be a build failure rather than a review comment. The
template already anticipates this — `just backend clean` removes `.import_linter_cache`, though the
tool was never added.

**Implemented** in `backend/pyproject.toml`. Three contracts landed with the package layout; a
fourth arrived with persistence:

```toml
[tool.importlinter]
root_package = "quookly"

[[tool.importlinter.contracts]]
name = "Calls flow downward through the layers"
type = "layers"
containers = ["quookly"]
layers = ["routes", "managers", "engines", "access"]
exhaustive = true
exhaustive_ignores = ["api", "utilities", "contracts"]

[[tool.importlinter.contracts]]
name = "Utilities do not depend on the layers that use them"
type = "forbidden"
source_modules = ["quookly.utilities"]
forbidden_modules = ["quookly.routes", "quookly.managers", "quookly.engines", "quookly.access"]

[[tool.importlinter.contracts]]
name = "Contracts depend on nothing else in the package"
type = "forbidden"
source_modules = ["quookly.contracts"]
forbidden_modules = [
    "quookly.routes", "quookly.managers", "quookly.engines",
    "quookly.access", "quookly.utilities",
]
```

```toml
[[tool.importlinter.contracts]]
name = "The ORM does not escape the access layer"
type = "forbidden"
source_modules = [
    "quookly.routes", "quookly.managers", "quookly.engines",
    "quookly.contracts", "quookly.utilities",
]
forbidden_modules = ["sqlmodel", "sqlalchemy"]
```

That last one needs `include_external_packages = true` on `[tool.importlinter]`, and it is
[ADR-018](#adr-018-sqlmodel-as-the-orm) made mechanical: the datastore stays swappable only for as
long as no business logic imports an ORM type.

`exhaustive = true` is the one that keeps the guard honest over time: a new top-level package that
is not declared as a layer fails the build rather than quietly escaping the rules.

**Contracts covering individual services are added alongside those services.** import-linter treats a
contract naming a module that does not exist as an *error*, not as a no-op — verified — so manager
independence and rule-engine purity cannot be declared before those modules are written. They land
with them:

| Contract | Type | Status |
| --- | --- | --- |
| Engines do not reach resource access | `forbidden` | **Active** since `MeasureEngine` (Phase 1) |
| Managers never import one another | `independence` | Arrives with the first two managers |

The engine contract — [ADR-006](#adr-006-allergen-determination-is-structural) expressed as a build
failure — is written against the whole `quookly.engines` package, because every engine today is a
rule engine. When a **capability** engine arrives, one that mediates the model or the search index,
this contract will break the build until it is rewritten to name the rule engines explicitly.

That is deliberate. An engine acquiring I/O should be a decision somebody makes and records, not
something that happens because a file was added to a directory.

**Guarding the guard.** `backend/tests/test_architecture.py` asserts both that the codebase conforms
*and* that each contract rejects a deliberately planted violation. A layering contract that silently
matches nothing is worse than no contract, because it looks like protection. The tests require the
linter to report a *broken contract* rather than merely exiting non-zero, so a linter error cannot
masquerade as a working guard.

**Cost.** One more dev dependency and a contract file to maintain as the package layout evolves.
The contract must be updated in the same commit as any package-layout change, or it silently stops
covering the thing it was written for.

---

## ADR-009 SQLite only to begin with

**Status:** Accepted

**Context.** NFR-1 and NFR-3 target self-hosting on modest hardware. Supporting two datastores from
the start doubles the testing surface before there is anything to test.

**Decision.** Ship **SQLite only**. Postgres is not supported at v1. The persistence volatility (V13)
is still encapsulated, so adding Postgres later is a change confined to the resource access layer
and its configuration.

**Rationale.** A household instance should not require a database server, and SQLite is sufficient
for the read-heavy, single-household workload Quookly actually has. Building Postgres support before
a single real query exists would be speculative work against unknown requirements.

Deferring is safe here specifically because the architecture already isolates the decision. Business
logic never sees a connection, a session, or a dialect — it calls domain verbs on resource access
services (V13). Combined with [ADR-018](#adr-018-sqlmodel-as-the-orm), the later swap is a
configuration change plus whatever dialect-specific code the access layer holds.

**Cost, and the honest limit of the abstraction.** Two things will *not* swap for free, and
pretending otherwise is how this decision goes wrong later:

- **Full-text search.** SQLite FTS5 and Postgres `tsvector` are different mechanisms, not different
  spellings of one. `SearchIndexAccess` exists so that difference is absorbed in one service, and it
  is where the strain will show first (V10).
- **Concurrency.** SQLite serialises writers. That is fine for a household and not fine for a shared
  community instance, which is the point at which Postgres stops being optional.

**When to revisit:** the first instance with concurrent writers, or the first search requirement
FTS5 cannot serve.

## ADR-010 The frontend never decides suitability

**Status:** Accepted

**Context.** Client-side filtering is faster and would feel more responsive.

**Decision.** The frontend renders suitability verdicts computed by the backend. It does not
implement the rules.

**Rationale.** A second implementation of a safety-critical rule will drift from the first. The
generated API client makes the backend verdict cheap to consume.

**Cost.** Filtering by suitability requires a round trip.

---

## ADR-011 Events for cross-manager reactions

**Status:** Accepted

**Context.** Cooking a meal must consume stock and award points. Publishing a recipe must award
points. The call rules forbid Manager→Manager.

**Decision.** Managers publish past-tense facts to an `EventBus`. `EngagementManager` subscribes.

**Rationale.** Satisfies FR-12 — scoring rules change without touching the code that publishes
recipes or cooks meals — and keeps the user-facing response off the scoring path.

**Cost.** Eventual consistency for points, and a bus to operate. In-process to begin with; the
interface allows a durable implementation later without changing publishers.

---

## ADR-012 Export format is the import format

**Status:** Accepted

**Context.** FR-11 requires lossless export. UC-1.2 requires JSON import.

**Decision.** One documented JSON schema serves both.

**Rationale.** A single format is tested by every round trip, and it is the concrete form of the
promise that self-hosters are not trapped. Two formats would mean the export path is exercised only
by people leaving.

**Cost.** The format becomes a public contract and must be versioned.

**Built.** Two properties make the format portable, and both were forced by asking what happens on
an instance that has never seen the recipe:

- **Lines refer to ingredients by slug.** Database ids belong to the instance that issued them; a
  slug means the same thing everywhere.
- **The ingredients used travel with the recipes.** Without their definitions, importing into a
  fresh instance would resolve nothing, and the promise would hold only between instances that
  already agreed.

Where an entry already exists locally, the **local one wins** — an instance's own densities are its
business and a document must not rewrite them. Imported entries are created as the importer's own,
so a document cannot forge a seeded row that an upgrade would later feel free to replace.

A document declaring a format version this build does not know is refused rather than partially
read: honouring the parts we recognise would silently drop whatever the newer format added.

**Adding an optional field does not bump the version.** Allergen classification arrived that way: an
absent `allergens` field means unexamined, which is exactly what a document written before it existed
knows. Removing or changing the meaning of a field would bump it.

---

## ADR-013 Cooking sessions are server-side state; timers store instants

**Status:** Accepted

**Context.** Cooking mode guides a cook through mise-en-place and steps, with per-step timers. The
cook is standing up with a phone that locks, a tablet that sleeps, and hands that are busy.

**Decision.** The session — current step, progress, timer state — lives on the server. Timers store
the instant they were started plus accumulated paused time; the client computes and ticks the
remaining display.

**Rationale.** Client-only session state dies with the tab, which fails UC-9.7 outright. Storing
*remaining seconds* rather than instants goes wrong the moment anything pauses, disconnects, or
resumes on another device, and a reduction that silently loses four minutes is worse than no timer
at all. Instants are the only representation that survives every interruption a real kitchen
produces.

**Cost.** A write on every step advance and timer action, and a resolution ceiling set by clock skew
between client and server. Neither matters at the granularity of cooking.

---

## ADR-014 Onboarding progress is derived, not stored

**Status:** Accepted

**Context.** New cooks need guiding through eaters, constraints, units, and locale. The obvious
implementation stores wizard progress.

**Decision.** `OnboardingEngine` derives what is missing from the profile data itself. No completion
flag is stored.

**Rationale.** A stored flag drifts from reality: delete every eater and the flag still says
complete. Deriving means the answer is always true, "resume later" (UC-10.3) needs no extra
machinery, and the same engine later powers profile-completeness prompts.

**Cost.** One distinction must be modelled explicitly: **"declared none" is not "not answered"**
(FR-15). A cook with no dietary constraints must be storable as *asked and answered none*, or
onboarding will nag them forever. This is the one piece of state the derivation cannot infer, and
missing it is the failure mode of this design.

---

## ADR-015 Mobile-first, installable, and offline where it matters

**Status:** Accepted

**Context.** Quookly is used in a shop and at a worktop. It is developed on a laptop.

**Decision.** Layouts are authored at the narrow viewport and widened. Quookly ships as an
installable PWA. The active recipe, the running cooking session, and the shopping list work offline.

**Rationale.** Designing wide and adapting down reliably produces the cramped mobile experience the
product exists to replace. Offline is not a general goal but a targeted one: shops have poor signal
and kitchens are often far from the router, and those are exactly the two moments Quookly is most
needed.

**Cost.** A service worker to maintain, cache invalidation to get right, and offline mutations —
ticking off shopping items, advancing steps — needing a reconciliation story. Confining offline to
three surfaces keeps that bounded.

---

## ADR-016 Ship seed content, marked and upgradable

**Status:** Accepted

**Context.** An empty instance is indistinguishable from a broken one, and gives neither a new user
nor a developer anything to work with.

**Decision.** Ship a locale-appropriate ingredient registry and a set of starter recipes as
versioned fixtures, loaded on first run and via a CLI command. Every record carries its origin.
Upgrades may replace seeded records and never touch user-created ones. Editing a seeded recipe
produces a user-owned variant.

**Rationale.** Seed content is the fastest route to a testable system and a usable first session
(UC-10.4). Marking origin is what makes it *upgradable* rather than a one-time dump that can never
be improved without risking user data. Reusing the existing variant relationship for edits avoids
inventing a copy-on-write concept.

**Built.** The seed file *is* an exchange document
([ADR-012](#adr-012-export-format-is-the-import-format)), so the format that carries a cook's recipes
out is the one that brings the starter set in — one format to maintain, already tested by every round
trip, and a self-hoster can supply their own.

Stocking the registry runs at start-up and is idempotent, and it never touches an entry that already
exists: a cook's own density is their business, and an upgrade refreshing the seed set must not
overwrite their work. Starter recipes are given to the first cook rather than owned by the instance,
so they are theirs to change — which is the point of a starter recipe, and avoids inventing a system
account nothing else needs.

**Cost.** The seed set must be maintained and translated per locale, and its licensing must be clean
— the same licensing discipline applied in
[ADR-007](#adr-007-nutrition-data-usda-fooddata-central-as-the-base) applies to any recipe content
not written for this project. Starter recipes should be authored for Quookly or taken from clearly
public-domain sources.

---

## ADR-017 Test-driven development with per-unit quality gates

**Status:** Accepted

**Context.** The architecture only pays off if it is maintained. Layering, documentation, and test
coverage all decay silently under delivery pressure.

**Decision.** Work proceeds test-first: read the specification, write the failing test, implement
until green. Every unit of implementation ends with the full gate — lint, typecheck, all tests,
a refactor pass, an architecture-alignment check, and a documentation update.

**Rationale.** The decomposition here makes TDD unusually cheap: rule engines are pure functions,
so their tests need no fixtures, no database, and no mocks. That is not an accident of the design,
it is one of its main benefits, and it is most valuable exactly where correctness matters most —
`SuitabilityEngine` (ADR-006) can be specified entirely as a table of inputs and expected verdicts.

Running the gate per unit rather than per pull request is what keeps the cost flat. A layer
violation caught immediately is a one-line fix; caught a week later it is a refactor.

**Cost.** Slower per unit, and it requires specifications precise enough to test — which is itself a
benefit, since a requirement that cannot be expressed as a test is usually one that has not been
understood.

**Procedure:** [Development](10-development.md#the-development-loop).

---

## ADR-018 SQLModel as the ORM

**Status:** Accepted

**Context.** [ADR-009](#adr-009-sqlite-only-to-begin-with) ships SQLite only, on the understanding
that moving to Postgres later stays cheap. Something has to make that true in practice.

**Decision.** Use **SQLModel** in the resource access layer. Models are defined once and serve as
both table definitions and typed structures. Async access uses `AsyncSession` from
`sqlmodel.ext.asyncio.session` over SQLAlchemy 2.0's async engine, which for SQLite means the
`aiosqlite` driver.

**Rationale.** SQLModel sits on SQLAlchemy, so dialect portability comes from a mature engine rather
than from hand-written SQL. It is Pydantic-based, which matches a codebase whose API contracts are
already Pydantic and which runs strict mypy — the same model definition carries the types rather
than being restated. It is also from the FastAPI author, so the integration path is well trodden.

**What actually guarantees the swap.** SQLModel makes it easier; **the resource access layer makes
it possible**. If business logic imported SQLModel types, the ORM would be part of the domain and no
amount of dialect abstraction would help. The rule stands: SQLModel types live in `access/`, and
what crosses upward is `contracts/`.

That rule is **enforced**, not merely stated — an import-linter contract forbids every layer except
`access` from importing `sqlmodel` or `sqlalchemy`, and a test plants a violation to prove the
contract bites ([ADR-008](#adr-008-enforce-the-call-rules-with-import-linter)).

**Cost.** One more layer between the code and SQLAlchemy, and SQLModel does not cover everything
SQLAlchemy exposes. The escape hatch is deliberate and cheap: because it is a thin layer, dropping
to SQLAlchemy directly *inside a resource access service* is possible without any caller noticing.

Migrations are Alembic, as they would be with SQLAlchemy alone.

---

## ADR-019 No default secret key

**Status:** Accepted

**Context.** The JWT signing key has to come from somewhere. A default in the source makes
development frictionless.

**Decision.** There is no default. In `production`, a missing `QUOOKLY_SECRET_KEY` is a startup
failure. In `development`, a throwaway key is generated per process.

**Rationale.** A key committed to the source would be identical on every self-hosted instance and
published in the repository — every instance forgeable by anyone who read it. Refusing to start is
the correct failure: loud, immediate, and impossible to ship past.

Development gets a generated key rather than the same treatment because the failure mode there is
harmless. Tokens do not survive a restart, which is a mild annoyance and a fair trade for having no
constant in the source. It also keeps the ergonomics promise: a fresh clone runs with no
configuration.

**Cost.** Sessions end on restart during development, which will occasionally confuse someone. The
alternative costs every production instance its security.

**Amended: a supplied key must be at least 32 bytes.** PyJWT warns that an HS256 key shorter than
the SHA-256 output weakens every token signed with it (RFC 7518 §3.2). Refusing a short key is the
same argument as refusing a missing one — `QUOOKLY_SECRET_KEY=hunter2` would otherwise start
happily and sign real tokens. The rule applies in development too: environment-dependent security
rules are harder to reason about than one rule, and the fix is a single command.

---

## ADR-020 Argon2 via pwdlib, tokens via PyJWT

**Status:** Accepted

**Context.** Password hashing and JWT libraries. Most FastAPI material — including, for a long
time, the official tutorial — pairs `passlib` with `python-jose`, so that is what a contributor is
likely to reach for.

**Decision.** Hash with **Argon2 via `pwdlib`**. Sign and verify tokens with **PyJWT**. Do not use
`passlib` or `python-jose`.

**Rationale.** Both of the conventional choices are effectively unmaintained, which is
disqualifying for security code specifically: an unfixed vulnerability in a hashing or token
library is not a bug, it is an exposure. `passlib` additionally depends on the `crypt` module,
removed from the standard library in Python 3.13. FastAPI's own documentation has moved to `pwdlib`
and PyJWT. Argon2 is the current recommendation for password hashing; `PasswordHash.recommended()`
tracks it rather than pinning our own opinion.

Verified against upstream sources in August 2026 rather than assumed — this is the kind of decision
that silently rots.

**Consequences.**

- Every verification path returns a value instead of raising. A malformed hash or a forged token is
  ordinary input to a public endpoint, not an exceptional condition, and an exception there is an
  unhandled 500 on an unauthenticated route.
- The signing algorithm is pinned on decode, so a token declaring `alg: none` is rejected before its
  claims are read. This is the classic JWT forgery and it is cheap to prevent.

**Cost, and a real limitation.** `argon2-cffi` brings a compiled extension, so the image needs the
wheel for its platform. More importantly: **tokens cannot be revoked before they expire.** There is
no token store, so a leaked token is valid for its remaining lifetime and a logout is client-side
only. `QUOOKLY_TOKEN_LIFETIME_HOURS` (default 12) is the only bound. Refresh tokens with a
server-side store are the fix, and are deferred rather than forgotten.

---

## ADR-021 Account management does need a manager

**Status:** Accepted. Reverses part of [ADR-002](#adr-002-four-managers-not-one-per-entity).

**Context.** ADR-002 rejected a user manager, reasoning that account lifecycle here is thin —
register, authenticate, edit profile — so a manager would be an empty shell, with authentication
living in the `Security` utility and profile data behind resource access.

Implementing the account endpoints refuted this in two ways at once.

**The architecture forbids the alternative.** A Client may not call Resource Access directly. With
no manager, the only way to build `POST /accounts` would have been a route calling `CookAccess`, and
the call rules — the ones now enforced by `import-linter` — prohibit exactly that. There was no
legal shape for the code without a manager. `Security` could not take the work either: a utility may
not call resource access, or it stops being usable by every layer.

**And the shell was not empty.** Written out, sign-in is: fetch the credential, verify the password
against a decoy hash when no account matches, refuse both cases identically, fetch the cook, issue a
token. Bootstrap is: check that no account exists, create one as admin, close the path. That is
sequencing with branching and ordering constraints, which is what a manager is for.

**Decision.** `AccountManager` sequences bootstrap, registration, and sign-in. Six managers now.

**Rationale.** It passes ADR-002's test rather than evading it: it encapsulates V12, it varies for
its own reasons — authentication mechanism, registration policy, bootstrap rules — and it changes at
its own rate, independently of recipes, planning, cooking, and engagement.

**Cost.** One more manager, and ADR-002's headline count is wrong twice over. That is the right
trade: the count was always a summary of the reasoning, not the rule itself.

**What this says about the method.** The decomposition was judged before the work was attempted, and
attempting it corrected the judgement. That is the process working. The signal to watch for is the
one described in the [development loop](10-development.md#when-the-architecture-resists): a change
that has no legal shape is telling you the decomposition is wrong, not that the rules are
inconvenient.

---

## ADR-022 Standard-library logging, configured in one place

**Status:** Accepted

**Context.** A self-hoster debugging a failure at dinner time has the logs and nothing else. They
need to be machine-readable where they will be shipped or grepped, and legible where a developer is
watching a terminal.

**Decision.** Structured logging on the standard library — a JSON formatter in `production`, a
human formatter in `development` — with a request id carried in a `ContextVar`. No logging
framework. `quookly.utilities.diagnostics.configure_logging()` is the **only** thing that
configures logging, including for migrations.

**Rationale.** The formatter is short enough to read in full, and every deployment runs this code,
so a dependency here should earn its place. The context variable is what makes the several lines of
one request findable together, which is the difference between a log and a pile of lines.

**Two properties that are easy to get wrong.**

- **Only our own handler is replaced.** An earlier version removed every root handler, which
  silences anything else that attached one — uvicorn, a test harness, a self-hoster's own
  configuration. The handler is named and only handlers of that name are removed.
- **Alembic does not configure logging.** The generated `env.py` calls `fileConfig`, which disables
  every existing logger by default; running migrations in-process therefore silenced the
  application. `env.py` calls `configure_logging()` instead, and `alembic.ini` carries no logging
  sections. Restoring those sections would reintroduce the bug.

Both were found by tests failing in the suite while passing alone — the classic shape of a
configuration side effect.

**Request bodies are never logged.** That is what keeps passwords out of the logs, rather than a
redaction filter that has to be kept in step with every new field. A test asserts a registration
password never reaches the log.

**Cost.** No log framework niceties — no bound loggers, no processor pipeline. If structured
context becomes common enough to want them, `structlog` can sit on top without changing callers,
since everything goes through `get_logger`.

---

## ADR-023 Theming by design tokens, themes as data

**Status:** Accepted

**Context.** Quookly should look distinctive on first run, and ship a small set of themes — light,
dark, playful, decorative — that a cook picks between. Self-hosters will want their own.

**Decision.** A fixed contract of **CSS custom properties** — colour roles, type, space, shape,
depth, motion, density — set on `:root` and overridden by `[data-theme='…']`. Components consume
tokens and nothing else. A theme is a block of values, not code.

**Rationale.** Themes become data. Adding one requires no rebuild, no component changes, and no
audit of what might have hardcoded a colour — which is exactly what makes a self-hoster's own theme
practical rather than a fork. Runtime switching is free, and `prefers-color-scheme` slots in as a
default rather than a special case.

Compiling a stylesheet per theme from SCSS variables was the alternative. It rules out runtime
switching, makes a user-supplied theme a build step, and multiplies the CSS payload for something
that must work offline on a phone.

Colours are referenced by **role**, never by name. Nothing says "blue"; it says `--primary`. Every
foreground token is paired with the surface it belongs on, so **contrast is checkable per token
pair** rather than per screen — which is how "WCAG AA in every theme" becomes a testable claim
instead of an aspiration.

**Density is deliberately not a theme.** Cooking mode raises `--density` because the cook is
standing a metre away, not because they prefer larger text. Tying it to theme choice would make
legibility a setting somebody has to find mid-recipe.

**Cost.** The token contract is a real interface and has to be maintained as one; adding a token is
a change every theme must answer. A component that hardcodes a value silently opts out of theming,
so this needs to be caught in review — and it is the reason the contract is small enough to hold in
your head.

---

## ADR-024 Own component primitives on CDK behaviour

**Status:** Accepted

**Context.** Roughly a dozen UI primitives are needed. Angular Material provides them.

**Decision.** No component library. Build the primitives, using `@angular/cdk` for behaviour —
focus trapping, overlay positioning, live-region announcements — which ships unstyled.

**Rationale.** Material carries a strong and widely recognised visual identity; the design language
here is meant to be distinctive, and fighting a framework's opinions costs more than writing a
button. It is also heavy for an application that must install to a phone and work offline. The
primitive set is small and mostly native elements with tokens applied.

The CDK is the right seam: the parts that are easy to get subtly and inaccessibly wrong — focus
management, overlays, announcements — are exactly the parts we should not reimplement, and they
arrive without any appearance attached.

**Cost.** Accessibility is ours to get right rather than inherited, which is why the
[accessibility rules](11-design-language.md#accessibility) are stated as non-negotiable and checked
per screen. Each primitive is one more thing to maintain. Revisit if the primitive set grows past
what a small design system can carry.

---

## ADR-025 Runtime locale, `$localize` catalogues, one artefact

**Status:** Accepted

**Context.** `en_GB`, `de_CH` and `fr_CH` ship at v1 (FR-10). Angular's default i18n compiles one
build per locale, served from `/en-GB/`, `/de-CH/` and so on.

**Decision.** One build. Locale is chosen at **runtime**: the catalogue for the selected locale is
loaded before bootstrap via `$localize`'s `loadTranslations`, and `LOCALE_ID` is provided from the
same choice so dates and numbers format correctly. Messages are authored with Angular's `i18n`
attributes and extracted with `just frontend extract-i18n`. Changing language reloads the
application.

**Rationale.** A build per locale contradicts the single-artefact promise (NFR-2): the image would
carry three copies of the application, and the backend's SPA fallback would have to choose between
them by URL or `Accept-Language` — one more thing for a self-hoster to get wrong.

It is also wrong for the household this is built for. A family instance may have members who want
different languages, and under a per-locale build that is a different URL rather than a setting.

Using `$localize` rather than a third-party runtime library keeps extraction, ICU plurals, and the
`i18n` attribute syntax on Angular's own supported path, with no extra dependency in something every
deployment runs.

**Cost.** Every locale's catalogue ships in the artefact, and switching language costs a reload
because translations are loaded once before bootstrap. Both are acceptable: the catalogues are text,
and changing language is rare.

**Locale is not just language.** `de_CH` is not `de_DE` with different strings — it implies
different units, number formatting, and ingredient names (V14). `LOCALE_ID` covers the formatting;
ingredient naming is per-locale data in the registry, not a translation.

---

## ADR-026 One OpenAI-shaped wire format, not a provider plugin system

**Status:** Accepted

**Context.** FR-8 requires at least one local and one hosted inference provider, and V3 lists
Ollama, vLLM, OpenAI, Anthropic and OpenRouter as things that vary. The obvious reading is an
abstraction with an implementation per provider.

**Decision.** `ModelAccess` speaks **OpenAI-shaped chat completions** and is configured by base
URL, model name and an optional key. vLLM, Ollama, llama.cpp, LM Studio, OpenAI, OpenRouter and
Together are all reached by pointing it somewhere different.

**Rationale.** Those providers already agree on the wire format; a plugin layer over them would
abstract a difference that is not there. One implementation satisfies FR-8 honestly — a local vLLM
and a hosted OpenRouter key are both ordinary configurations of it — and the thing that actually
varies, *which model answers and how it is reached*, is exactly what the settings hold.

Structured output is requested as `response_format: json_schema` with `strict`. Verified against a
local vLLM serving Qwen3.6-35B: the model fills the shape rather than describing it.

**Cost.** A provider that speaks something else — Anthropic's Messages API is the obvious one — is
not reachable by configuration and needs its own access service. That is a real limitation, and the
right shape for it: a second implementation of `ModelAccess`'s interface rather than a plugin
protocol designed before there was a second thing to plug in.

An answer refused for being the wrong shape is not repaired. A fenced answer has its fence removed
— models add those often enough that refusing them wastes good answers — but what is inside still
has to parse on its own, and an answer cut short by the token limit is refused even when what
arrived happens to parse. For a recipe, truncation means missing ingredients.

---

## ADR-027 An instance will not fetch its own network

**Status:** Accepted

**Context.** UC-1.3 has a cook paste a URL, which the server then fetches. The URL is user input
and the fetch runs inside whatever network the instance sits in — a home LAN, a container network,
a cloud VPC.

**Decision.** `WebContentAccess` fetches only `http` and `https`, and only addresses that are
globally routable. Loopback, link-local, and the private ranges are refused. Every redirect hop is
checked, not only the URL that was pasted. A self-hoster who genuinely wants to import from
something on their own network sets `QUOOKLY_ALLOW_PRIVATE_FETCH=true`.

**Rationale.** Without it, a pasted link is a way to make the server read things the person pasting
it cannot: a router's admin page, a cloud metadata endpoint, Quookly's own API from inside. That is
worth guarding even on a single-user instance, and it is the sort of guard that is cheap now and a
retrofit later.

**Cost.** Two real ones, both stated rather than papered over.

The name is resolved for the check and resolved again by the connection, so a server that answers
differently the second time is still reachable. Closing that needs the resolved address pinned
through the connection, which the HTTP client does not offer without a custom transport. The
realistic case this stops — a link to `localhost` or to `169.254.169.254` — does not need that
sophistication.

And a self-hoster whose recipes live on their own network has to find a setting. That is the right
way round: the safe behaviour is the default, and the person who wants the other one knows why.

---

## ADR-028 Structured metadata is fetched, not preferred

**Status:** Accepted

**Context.** Most recipe sites embed `schema.org/Recipe` as JSON-LD. Checked against real pages,
BBC Good Food, Allrecipes and Jamie Oliver all publish a complete recipe that way — name, yield,
ingredient list, ordered instructions — which is a better answer than any interpretation of the
surrounding prose.

**Decision.** `WebContentAccess` returns the readable text **and** every embedded JSON-LD block,
without preferring either. Choosing between them is `InterpretationEngine`'s job.

**Rationale.** Which source to believe is the product's core competence and will be refined
indefinitely — that is the definition of V2. A page may carry a stale metadata block and a correct
article, or the reverse. Deciding in the access layer would put the most volatile judgement in the
least volatile place.

**Cost.** The engine receives two representations and has to reconcile them, which is more work
than being handed one. That work is the thing the engine exists to do.

---

## ADR-029 An ingredient the registry does not know is recorded and reported

**Status:** Accepted

**Context.** Importing from a URL produces ingredient *names*. Most resolve against the registry.
Some do not — "oil or melted butter" is a real line from a real page, and no registry will hold it.

**Decision.** An unresolvable name is **recorded** as a new registry entry with no density and no
allergen classification, and **reported** in the import's result. It is neither refused nor added
silently.

**Rationale.** The three options are not equal. Refusing the whole import over one unknown word
would make the feature useless — a cook pastes a link and gets nothing. Adding it silently would
leave them unaware that something needs checking. Recording and reporting keeps the recipe usable
while making the gap visible.

Crucially the new entry is **unexamined**, not examined-and-clear (ADR-006). Nothing is known about
its allergens, so any recipe using it reads as *unknown* rather than as safe — which is the true
answer, and one the cook can see and act on.

**How resolution reaches the registry.** A written name is tried in several forms, most specific
first: "3 large free-range eggs", then "eggs", then "egg". Words that say *which one to buy* —
large, free-range, organic, fresh — are dropped; words that change *what a thing is* are not.
"Whole" is pointedly in the second group, because whole milk is not milk, and dropping it would
attach a dairy allergen to nothing and misweigh the recipe besides. Without this the registry
gains an unclassified duplicate for eggs and an egg allergy stops firing on it.

**Cost.** A registry accumulates entries a cook never chose to add. They are marked as theirs
rather than seeded, so an upgrade will not touch them, and curating them is a Phase 9 concern.

---

## ADR-030 A recipe whose yield cannot be read is refused

**Status:** Accepted, and expected to be revisited

**Context.** A yield is the denominator of every quantity in a recipe. `InterpretationEngine`
leaves one absent when the page does not say — "a generous amount" is not a number — and the
domain currently requires one.

**Decision.** Such an import is refused, with a message saying the page does not state a yield and
suggesting the recipe be added by hand.

**Rationale.** The alternative is to invent one, and a yield of "1 serving" on a recipe that serves
four misscales every ingredient by a factor of four — silently, and in the direction a cook cannot
see. Refusing is the honest answer, and against five live pages it did not fire once.

**Cost.** A cook loses the whole extraction over one missing field, which is a poor trade. The
remedy is the same shape as the one made for unmeasured lines: let a recipe record that it does not
know its own yield. That is a wider change — scaling, planning and the shopping list all assume a
yield exists — and it waits until something makes it worth doing.

---

## ADR-031 An imported recipe is resolved in the page's own language

**Status:** Accepted

**Context.** Quookly ships in en-GB, de-CH and fr-CH, and a Swiss cook pasting a link to a Swiss
recipe site is the ordinary case. The registry is *defined* in English — slugs, densities, allergen
classifications — and until now it was only *named* in English.

**Decision.** The registry carries names in every locale Quookly ships (`seed/names.<locale>.json`),
and an import resolves ingredients in the page's own language: what `<html lang>` declares, else the
cook's chosen language, else English.

**Rationale.** This is a safety matter rather than a convenience. Asked in English, "Mehl" resolves
to nothing, is recorded as a new entry nobody has classified, and the recipe silently loses the
gluten the registry knew about. A German recipe made of flour, milk and eggs would carry no allergen
judgement at all — while looking exactly like one that had been judged and found clear.

The language is taken from the page rather than guessed from the words: the page knows, and guessing
from a short ingredient list would be a coin toss.

**Cost.** Translations are curated by hand and can be wrong or missing, and a missing one fails
quietly — the ingredient simply does not resolve. A test asserts every seeded ingredient is named in
every shipped language, which turns the silent case into a loud one.

A name means one thing per language: the unique index is on locale and spelling, so the first entry
to claim a word keeps it. That is why "Milch" is whole milk rather than being shared, and why
translations are added rather than overwritten.

**A related correction.** Separated eggs turned out to need their own entries. Resolving both
*Eigelb* and *Eiweiss* to "egg" printed "3 egg" twice on a recipe using three eggs, which reads as
six. `egg-yolk` and `egg-white` are now seeded ingredients in their own right, both classified as
containing eggs.

---

## ADR-032 (Proposed) Recipes are stored in their own language and read in yours

**Status: Proposed. Not built.** Recorded now because Phase 3 made the question unavoidable: an
import from swissmilk.ch produces a recipe whose ingredient names resolve into any language and
whose *steps* are German forever.

**Context.** Quookly ships in three languages and imports from the whole web. Four kinds of text
live in a recipe, and they are in very different positions.

| | Language-neutral already? |
| --- | --- |
| Quantities — magnitude and a `Unit` | Yes. Rendered per cook. |
| Durations and temperatures | Yes. Columns, not prose. A timer works in any language. |
| Ingredient names | **Yes, already built.** The registry is defined in English and named per locale; `RecipeAccess.fetch(recipe_id, locale)` resolves names for the reader. |
| Step instructions, title, summary | **No.** Stored exactly as written. |

So most of this is done. What remains is prose.

**Decision (proposed).** Three parts.

**1. A recipe records the language it is written in.** Imported from `<html lang>`, chosen when
authored. Without it nothing downstream can tell a German recipe from an English one.

**2. The original text is never replaced.** A canonical English rendering is stored *alongside* it,
and other languages are derived from that — 1→N rather than N→N, which is the real argument for
normalising. But the author's words stay.

This is where the proposal departs from "normalise to English on import". Discarding the source
makes every translation error permanent and unverifiable, and takes a German cook's own recipe away
from them in their own kitchen. Keeping the original costs a column and makes every translation
re-derivable when the model improves — which it will, faster than the recipes change.

**3. Translation is lazy and cached.** Rendered on first request for a language and stored, not
eagerly at import. Eager translation spends three model round trips on content nobody may read, and
makes adding a fourth language a migration over every recipe ever imported instead of a no-op.

**Rationale.** The pieces are already in place. `ModelAccess` reaches a model; `InterpretationEngine`
established the capability-engine shape and the import-linter contract that keeps it honest; the
registry already answers in three languages. `TranslationEngine` is the same shape as
`InterpretationEngine` pointed at a different question.

**The safety line is unaffected, and that is not an accident.** Allergen and suitability conclusions
come from the structured ingredient set, never from prose (ADR-006). A translation cannot make a
recipe read as safe, because no verdict has ever consulted prose. This is the first real dividend of
that rule: an entire feature can be built over machine-generated text without any of it touching the
safety path.

**Open questions, to be settled when this is built.**

- What happens to a translation when its source step is edited? The cheap answer is to drop it and
  re-derive; the honest one may be to mark it stale and show the original meanwhile.
- Can a cook correct a translation, and does that correction survive a re-derivation? A human
  correction that a model silently overwrites is worse than no correction.
- Does a shared or published recipe (Phase 8) carry its translations, or does each instance derive
  its own? Carrying them spreads one instance's model quality to everybody.
- Does the interchange format carry them? It does not yet carry the registry's per-locale names
  either, which is the same gap one layer down.

**Cost.** A table of translations, a per-request cache decision, and a dependency on a model for
something a cook may reasonably expect to work offline. An instance with no model configured must
degrade to showing the original — which is exactly what it does today, and is not a failure.

---

## ADR-033 The inference provider is configured by environment, and reported by the app

**Status:** Accepted

**Context.** UC-8.2 asks for the inference backend to be configurable, and FR-8 requires provider and
model to be *configuration, not code*. The obvious reading is a settings form that writes to the
database.

**Decision.** Configuration stays in `QUOOKLY_INFERENCE_*` environment variables. What the
application provides is a **report**: an administrator-only view of what the instance is pointed at
and whether it answers, on the settings screen and through `quookly-cli inference status`.

**Rationale.** A self-hoster's container, compose file or systemd unit already speaks environment
variables, and that is where the rest of this instance's configuration lives. Adding a database
override would create two sources of truth for the same setting and a class of question — "why is my
env var not taking effect" — that has no good answer.

An API key in the database is also a key in every backup of that database, in plaintext, and a key
in a settings form is a key in a browser's autofill. Neither is wrong forever, and neither is worth
doing before somebody actually needs it.

The reporting half is where the value is anyway. An operator's questions are "is a model configured"
and "does it answer", and until now the only way to find out was to try an import and read the
failure.

**What is reported, and what is not.** The address, the model, whether a credential is set, and
whether the provider answered — with a reason when it did not, because *could not reach it* and
*check the key* send somebody to two different places. Never the credential itself: a status page
that prints a key has published it into a screenshot, a support thread, a browser cache.

Administrators only. It names an address on the operator's network, which is a map of what the
server can see.

The reachability probe has its own short timeout rather than a completion's. A model that is slow to
answer is working; one that is slow to list its own models is not, and an operator staring at a
status page for three minutes has learned nothing except that.

**Cost.** Changing provider means restarting the instance. For a container that is the ordinary way
to change any setting; for somebody running it by hand it is a papercut. A database-backed override
remains available later, and would be a considered addition rather than the default.

---

## ADR-034 Stock is held as lots, not as a total per ingredient

**Status:** Accepted

**Context.** The obvious model for a pantry is one row per ingredient with a running quantity: two
kilos of flour, six eggs. It is smaller, it never needs grouping, and it is what a shopping list
wants to read.

**Decision.** Stock is held as **lots**. A lot is some of an ingredient that arrived at one time,
with one date on it and one note about where it came from. The pantry screen groups lots by
ingredient and totals them; storage keeps them apart.

**Rationale.** Expiry belongs to a packet, not to an ingredient. Two bags of flour bought a month
apart are the same ingredient and two different questions, and a per-ingredient total can only carry
one date — so it either takes the earliest, and warns about two kilos when 200 g are at risk, or
takes the latest, and never warns at all. Both are wrong in the direction that produces waste, which
is the thing this product is trying to reduce.

Reservations need the same granularity for the same reason. A plan reserves *stock*
([ADR-004](#adr-004-plans-reserve-stock-cooking-consumes-it)), and reserving against a total cannot
express "the carton that goes off on Thursday" — which is exactly the reservation a cook wants a
planner to make.

**Cost.** Every read has to group, and a total has to be computed rather than stored. A cook who
buys the same thing weekly accumulates lots, and the screen has to stay legible as they do. The
grouping lives in `PantryManager` so that no client re-derives it.

A depleted lot keeps its row, at zero, rather than being deleted: waste records point at it, and
they are the history the cook is trying to shrink. It leaves every listing, so an empty packet never
appears on a shelf or in an expiry warning.

**Where a total is refused.** Six eggs and 200 g of egg have no sum. The total is reported as
absent rather than approximated — every lot is listed underneath, so declining to invent a number
hides nothing.

---

## ADR-035 Adjusting stock and recording waste are different acts

**Status:** Accepted

**Context.** UC-5.3 and UC-5.4 both reduce a quantity. It is tempting to implement one verb — "the
amount changed" — with an optional reason attached.

**Decision.** Two operations, two endpoints, two stored facts. **Adjusting** restates what is
actually there: the number was wrong and is now right, and nothing left the kitchen. **Recording
waste** says food existed and was thrown away, and writes its own record carrying the ingredient,
the amount, the reason and the date.

**Rationale.** Only one of these is the number this product exists to bring down. A single verb
could never tell them apart afterwards, and waste inferred from a falling quantity is
indistinguishable from food that was eaten — which makes every waste figure derived from it
fiction.

The reasons are worth asking for, and `SPOILED` and `EXPIRED` are deliberately kept apart. Food that
actually went off was bought or stored badly. Food binned on its date was very often still fine, and
that is the waste a cook can most easily stop. Collapsing the two into "off" discards the only
distinction worth acting on.

**Adjustment is a restatement, not a difference.** A cook looking into a jar knows how much is in
it, not how much has gone since they last looked. A difference sent twice by a flaky connection
subtracts twice; a restatement sent twice says the same thing twice.

**Deleting a lot is a third thing.** A lot entered by mistake never existed, so it is removed
outright rather than wasted — food that was never in the house must not land in the figure the cook
is trying to reduce. Once anything has been thrown away from a lot, deleting it is refused: the
waste record would be left pointing at nothing, and the history would quietly shrink.

**Cost.** Two endpoints and two forms where one would do, and a cook who does not care about the
distinction has to pick a reason anyway. The reasons are five coarse choices with a sensible one at
the top rather than a free-text box, so the cost is one tap.

**What is not built yet.** The waste *report*. UC-5.* asks for waste to be recorded, not summarised,
and a chart of it belongs with the rest of the reporting surface. The records are complete from the
first one, so the report can be written later without a migration — which is the whole reason for
storing the fact rather than the subtraction.
