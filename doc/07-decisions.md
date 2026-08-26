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

**Status:** Accepted, and **amended by
[ADR-045](#adr-045-composition-data-is-tried-in-a-configured-order-nearest-table-first)**, which
demotes USDA from the base set to the last resort. The licensing work below stands unchanged and is
why USDA remains in the list at all; the claim that "nutrient values for generic ingredients travel
well across borders" does not, and ADR-045 says why.

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

**Versioning, as exercised by the changes to the format.** A build **writes one version and reads
several**. Format 2 added a recipe's `serves`; format 3 added each step's `attention`. Older
documents still import, and one of them is a complete recipe that simply does not say those things.

The version was bumped rather than the field quietly added to format 1, and that is the whole point
of having a version. An older build reading a document with an unknown field would drop it in
silence — the partial honouring this check exists to prevent. Refusing outright tells the operator
what happened. Meanwhile, refusing every document a self-hoster has *already* exported, to gain one
optional field, would break the promise the format exists to keep.

So: `FORMAT_VERSION` is what this build writes, `READABLE_VERSIONS` is what it accepts, and a
version outside that set is refused with both named.
Where an entry already exists locally, the **local one wins** — an instance's own densities are its
business and a document must not rewrite them. Imported entries are created as the importer's own,
so a document cannot forge a seeded row that an upgrade would later feel free to replace.

A document declaring a format version this build does not know is refused rather than partially
read: honouring the parts we recognise would silently drop whatever the newer format added.

**What owes a bump is not "is the field optional".** Allergen classification arrived without one: an
absent `allergens` field means unexamined, which is exactly what a document written before it existed
knew, and an older build reading a newer document reaches the same conclusion the newer one does.

The test is whether an older build would silently produce a **different recipe**, rather than a less
complete record of the same one. `serves` and `attention` both fail it. Dropping `serves`, a recipe
that could be scaled to a table can no longer be; dropping `attention`, a cake's ninety minutes in
the oven are reported as ninety minutes of work. Neither reader would know anything had gone wrong,
which is why both bumped. Removing a field or changing what one means always bumps.

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

**As built.** Two refinements, both in the direction of the same argument.

*Elapsed rather than paused.* A timer stores the instant it was last started plus the seconds it had
already counted, which carries the same information as "start plus accumulated pause" and needs one
subtraction rather than two. It also degrades better: a client clock ahead of the server's is clamped
at zero, because a timer that goes *up* when you pause it is a timer nobody believes again.

*A timer per step, not per session.* UC-9.4 says "a timer belonging to a step", and a real kitchen
has the oven on while something else simmers. One timer per session would have made the cook choose
between them.

Nothing here is a countdown. The server never computes remaining time and the client never sends one,
which is what lets a locked phone and a tablet in the other room agree about how long the sauce has
had.

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

**As built, the widening was owed.** For five phases "authored at the narrow viewport and widened"
was only half done: everything was authored narrow and nothing was widened, which is the failure
mode this ADR invites if the second half is never scheduled. A laptop got a phone layout with margin
either side. The correction — real breakpoint mixins, chrome that becomes a sidebar, collections
that become grids — is recorded in the design language's Layout section, and an end-to-end suite
(`e2e/14-widths.spec.ts`) now asserts at 390px, 834px and 1440px that no page scrolls horizontally
and that the chrome is in the right place, so the second half cannot silently lapse again. It found
a real defect on its first run: `/plans` had overflowed a phone by 12px since the day it was written.

**As built, for the cooking session.** The reconciliation story turned out to be smaller than
feared, because of what these mutations *are*.

*Where the cook is* is a position, not an increment. Held locally and re-sent when the network
returns, last write wins — and last write wins is not a compromise here, it is the correct answer:
the server does not need the steps in between, only where the cook ended up.

*A timer* is the one thing that cannot be done offline, and it says so rather than pretending. Its
whole design is that the server stamps the instant
([ADR-013](#adr-013-cooking-sessions-are-server-side-state-timers-store-instants)); one stamped on
the way back would quietly lose however long the connection was down, which is the failure that ADR
exists to prevent. A timer already running keeps counting, because that is arithmetic on instants
the device already has — and it is the common case, since the connection usually drops *after* the
pan is on.

*Reading* is served by keeping the last answer the server gave, keyed and cleared whenever anybody
signs in or out — **not** by the service worker's data cache. That caches by URL, and a URL here
answers differently depending on who is asking: two people sharing a tablet would see each other's
meals.

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

**Revisited in part.** This record also noted, via the
[domain model](06-domain-model.md#appetite-multiplier), that a yield of "12 pancakes" cannot be
scaled to a table at all. Planning is what made that worth fixing, and a recipe now carries
**`serves`** beside its yield: makes 12, serves 4. `MeasureEngine.scaling_for` reads whichever of
the two answers, and refuses only when neither does.

Absent stays a real answer. Nothing infers a pieces-per-serving figure — from the page, from the
model, or on the way to the screen — because a wrong one would misportion every meal planned from
that recipe, silently and in the direction a cook cannot see.

The *other* half — a recipe that does not know its own yield at all — is still refused, and still
waiting for something to make it worth doing.

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

---

## ADR-036 A reservation exists only while it is held

**Status:** Accepted

**Context.** [ADR-004](#adr-004-plans-reserve-stock-cooking-consumes-it) settled that planning
reserves and cooking consumes. It did not settle how a reservation is stored, and the obvious
model — a row with a status of `held`, `consumed` or `released` — carries the history for free.

**Decision.** A reservation row exists **exactly while the claim is held**. Releasing deletes it;
cooking decrements the lot and deletes it. There is no status column.

A reservation is against a **lot**, not an ingredient. How much of a lot is free is **computed** from
the claims against it, never stored.

**Rationale.** A status is a second thing to get right on every read. Every availability query would
have to filter on it, and the cost of one query forgetting is stock that is neither free nor gone —
invisible forever, which is precisely the failure ADR-004 exists to prevent and precisely the waste
this product exists to reduce. A row that exists only while it means something cannot be misread:
if it is there, the claim is held; if it is not, it is not.

Nothing is lost. What actually happened to food is recorded elsewhere and better: waste has its own
record ([ADR-035](#adr-035-adjusting-stock-and-recording-waste-are-different-acts)), and a meal
having been cooked is a fact about the cooking session, not about a reservation. A released
reservation has no history worth keeping — the butter is still in the fridge, and nothing happened.

Against a lot rather than an ingredient because that is the reservation worth making: "the carton
that goes off on Thursday", not "some milk"
([ADR-034](#adr-034-stock-is-held-as-lots-not-as-a-total-per-ingredient)). Two plans cannot claim the
same carton, and the shopping list falls out of what could not be claimed.

A stored `reserved` column beside the quantity would be a second source of truth about the same
butter, and the two would disagree the first time anything failed halfway through. Computing costs a
join per query, on a household's worth of rows.

**The fridge wins over the plan.** A cook who says there are 100 g left when a meal has claimed 400 g
is telling the truth about their own kitchen. The claim yields, not the report — and what it yielded
is returned, so a caller can say which meal now needs shopping for. The claim is **cut down rather
than dropped**: 300 g claimed against 100 g remaining is a claim on 100 g, and freeing all of it
would give away stock the meal is still going to use. Where several claims must yield, the newest
goes first: something has to, and "last to ask, first to go" is a rule a person accepts without
needing it explained.

Recording waste takes the same path, because waste is also a fall in what is there.

**Release is not an error path.** Cancelling a plan, moving a slot to another recipe and abandoning
a cooking session all release, and each is an ordinary thing to do. Releasing a meal that holds
nothing is therefore not a failure — cancelling a plan releases every slot, and most slots hold
nothing.

Two deletions are refused rather than cascaded: a plan slot that still holds stock, and a lot a
planned meal is counting on. Both would leave a claim pointing at nothing. Making the order an error
rather than a cascade is what makes it impossible to get wrong, and the refusal sends the cook to
the meal that needs replanning instead of silently breaking it.

**What the pantry screen does with a released claim: nothing.** The place to learn that Thursday
dinner is short is the plan, where it is derived from the reservations and is therefore always
right. A passing message on the pantry screen would be a second and weaker channel for the same
fact. The information crosses the access boundary anyway, because a caller that *does* need it must
not have to work it out again.

**Cost.** No answer to "what was this stock reserved for last week". If that question is ever worth
asking, it is a log of plan changes rather than a status column on a live claim — a different table,
written for that purpose, and not one that any availability query has to read.

---

## ADR-037 How long a recipe takes is two numbers, both derived

**Status:** Accepted

**Context.** A recipe has no time on it at all, which is a real gap: "how long does this take" is one
of the first two questions anybody asks of a recipe, alongside "can we eat it". Every recipe site
answers it, usually with a single figure.

A single figure is worse than none. A cake is twenty minutes of work and ninety minutes of waiting;
shown as "1 h 50" it reads as a weekend project when it is a Tuesday-evening one with a gap in the
middle. Bread shown as "30 min" — its hands-on time — reads as a half-hour job, and somebody starts
it at six and eats at midnight. Both numbers are true and each alone is misleading.

**Decision.** A recipe reports **two** numbers:

- **Hands-on time** — how long the cook has to be doing something.
- **Total time** — how long from starting to eating.

Both are **derived from the steps**, never stored as recipe fields.

Each step gains an **attention** of its own, provisionally three values:

| Attention | Meaning | Counts towards |
| --- | --- | --- |
| Hands-on | The cook is doing something — chopping, stirring, shaping | Hands-on and total |
| Waiting | It is cooking and the cook is around — baking, simmering, resting | Total only |
| Ahead | It happens without the cook — proving overnight, marinating, chilling | Neither; surfaced as *"start the day before"* |

**Rationale.** The two numbers answer two different questions, and a cook asks both. *Can I do this
tonight* is hands-on time. *When do we eat* is total time. Collapsing them loses whichever question
the reader was actually asking.

The third category is not a third number. Soaking beans overnight is eight hours in which the cook
is asleep; adding it to a total makes an ordinary dish read as a nine-hour ordeal, and dropping it
silently means somebody starts dinner at six and discovers the beans needed starting yesterday.
Surfacing it as a lead — *start the day before* — is the only framing that is neither alarming nor
a trap. Cooking mode already needs long-lead work brought forward
([V15](03-volatility-analysis.md#v15-execution-guidance) names it), so this is the same fact serving
two purposes.

**Derived, not stored,** for the reason onboarding progress is derived
([ADR-014](#adr-014-onboarding-progress-is-derived-not-stored)) and free stock is computed
([ADR-036](#adr-036-a-reservation-exists-only-while-it-is-held)): a stored total is a second source
of truth that is wrong from the first step edited. The derivation belongs in `ExecutionEngine`,
whose charter already includes which steps can run in parallel — and overlap is exactly why total
time is not the sum of the durations. *While the oven heats, make the batter* is two steps and one
stretch of clock.

**Unknown stays unknown.** A step with no duration must not contribute zero. Zero is a lie in the
direction that makes every recipe look quicker than it is, and a cook who is late for dinner once
because of it stops reading the number at all. Where any step's duration is missing, both totals are
reported as **lower bounds** and marked as such — "at least 25 min hands-on". The same rule as an
unclassified allergen ([ADR-006](#adr-006-allergen-determination-is-structural)), an unresolved
ingredient ([ADR-029](#adr-029-an-ingredient-the-registry-does-not-know-is-recorded-and-reported))
and an unreadable yield ([ADR-030](#adr-030-a-recipe-whose-yield-cannot-be-read-is-refused)): this
codebase does not let absence read as a value.

**Not a new volatility.** What varies — whether stirring occasionally is hands-on, how overlap is
inferred, whether waiting by the hob counts as work — is judgement about steps, which is
[V15](03-volatility-analysis.md#v15-execution-guidance). A service of its own would encapsulate
nothing that `ExecutionEngine` does not already own.

**What it unlocks.** V7 already names *"optimisation for effort on weeknights"* among the ways
planning strategy varies, and it has had nothing to optimise against. UC-3.2 offers filtering by
time. Both become possible the moment this exists.

**Import gets it nearly free.** schema.org/Recipe publishes `prepTime`, `cookTime` and `totalTime`.
They map imperfectly — `prepTime` is roughly hands-on, `cookTime` roughly waiting — but a recipe
imported with them is better off than one imported without, and the model already reads prose into
structure where the metadata is absent.

**Cost.** A column on every step, a migration, and a question on the step form that most authors
will leave alone — so the default has to be right. *Hands-on* is the safe default: it over-reports
the work rather than under-reporting it, which fails in the direction that does not make anybody
late.

Derived values cannot be indexed, so filtering a large collection by time would eventually want a
cached column recomputed on write. That would be explicitly a **cache**, invalidated by any step
edit, and never the thing the recipe screen reads.

**Built** in Phase 5, in `ExecutionEngine`. Two things settled differently in the building than they
were framed here.

**Overlap is not inferred, and the total is sequential.** This decision was deferred to Phase 5 on
the grounds that the number is only honest once something knows about parallelism. Writing it made
the opposite case: a recipe never says which of its steps overlap, so any inference is a guess, and a
guess makes the total *shorter* than the truth. That is the one direction that makes somebody late —
the exact failure this ADR exists to prevent. Adding the durations up over-reports, which is safe,
and a cook who wants the overlap counted writes it as one step. That is also how they would say it
out loud: *while the oven heats, make the batter* is one instruction, not two.

So the number was honest immediately, and the deferral bought nothing except that the field arrived
alongside cooking mode, where the same attention decides what a session surfaces ahead of time.

**Absence goes all the way up.** A step with no duration makes its total a lower bound, as decided.
Where *nothing* of a kind was timed, there is no number at all rather than a floor of zero: "at least
0 min hands-on" would tell a cook the cake makes itself. The three numbers are absent independently,
so a recipe can report exact work and an unknown clock.

---

## ADR-038 A plan's reservations are restated, not adjusted

**Status:** Accepted

**Context.** [ADR-004](#adr-004-plans-reserve-stock-cooking-consumes-it) settled that planning
reserves and [ADR-036](#adr-036-a-reservation-exists-only-while-it-is-held) settled how a claim is
stored. Neither says what happens when a plan *changes* — and a plan changes constantly, which is
what planning is.

The obvious approach adjusts: work out the difference a change makes and reserve or release that
much.

**Decision.** Every change to a plan **releases every claim it holds and makes them again from
scratch**. There is no incremental path.

Reading a plan never writes. The week is presented from the claims that exist, and the shopping list
is what those claims do not cover.

**Rationale.** "The plan's reservations match the plan" becomes true by construction rather than by
remembering. The incremental version needs arithmetic that stays right across every kind of edit —
a recipe swapped, a guest added, a meal moved to Thursday, an appetite corrected, a slot emptied —
and the one that is got wrong leaves stock spoken for by a meal nobody is cooking. That stock is
invisible forever, which is the failure ADR-004 exists to prevent.

Same argument as restating an eater's constraints wholesale: a merge needs a way to say *and let
this one go*, and the version that forgets to is the one that keeps something the cook removed.

**Reading never writes** for a plainer reason. A GET that reserved would reserve twice when a plan is
opened on a phone and a tablet, and a shopping list would grow by being looked at.

**The shopping list is read from the reservations**, not worked out a second time from what is on the
shelf. FR-7 says the list is the requirement net of stock; two calculations of that are two answers,
and the day they disagree is the day a cook trusts neither. So netting decides what to reserve, and
the list is the remainder of the requirements the reservations did not cover — derived *from* them,
so it cannot contradict them.

**Cost.** More writes than an adjustment would make: a week of twenty-one slots re-reserves all of
them when one changes. On a household instance that is a few dozen rows, and the alternative buys
speed with a class of bug that cannot be seen from the interface.

Between the release and the re-reserve, this plan's stock is briefly free. On a single-household
instance nothing else is looking; on a shared one a concurrent plan could take it, and the shortfall
would simply grow. Worth revisiting if households ever share a pantry — which is
[an open question](06-domain-model.md#open-questions) already.

---

## ADR-039 Events are published in this process, and awaited

**Status:** Accepted

**Context.** Cooking a meal has to consume the stock that meal reserved. `PlanningManager` owns the
plan and `PantryManager` owns inventory truth, and a Manager may not call a Manager
([ADR-002](#adr-002-four-managers-not-one-per-entity)). The architecture named the `EventBus` as the
answer before there was anything to carry.

The question this record settles is not *whether* a bus, but what kind. A queue, a background task,
and a plain function call dressed up are all in the space.

**Decision.** An **in-process** bus. `publish` **awaits every listener** and **lets a failure
propagate**. There is no persistence, no retry, and no ordering beyond registration order.

Subscriptions are wired where the application is assembled — `api.py` — rather than as an import
side effect of a manager.

**Rationale.** Fire-and-forget would make publishing cheap and make the consequences invisible. A
meal recorded as cooked whose stock was never consumed is stock reserved forever: neither free nor
gone, which is exactly the failure
[ADR-004](#adr-004-plans-reserve-stock-cooking-consumes-it) exists to prevent and exactly the waste
the product exists to reduce. The publisher does not learn *who* failed — only that the fact could
not be fully acted on, which is enough for it to refuse to pretend otherwise.

Awaited and propagating makes the bus look like a function call with extra steps. What it buys is
the thing that matters: `PlanningManager` does not import `PantryManager`, does not know stock
accounting exists, and a cooking session (Phase 5) will publish the same `MealCooked` without either
of them learning about the other. That independence is the point; the asynchrony is not.

**Ordering, and what happens when a listener fails.** Listeners run in registration order and the
first failure stops the rest. With one listener doing real accounting that is the safe reading. The
day an advisory listener sits beside an essential one — engagement points beside stock — is the day
this needs splitting into "must succeed" and "may fail", and not before. Recorded so the next person
does not have to rediscover why it is this way.

**The publisher states the fact before recording it.** Cooking publishes `MealCooked` and *then*
marks the slot. If marking fails, the cook marks it again: the claims are already gone, consuming
none consumes nothing, and the second attempt lands. The other order would leave a meal recorded as
cooked whose stock was never taken. Idempotent listeners are what make this safe, and they are cheap
here because "consume what this meal holds" is naturally empty the second time.

**Wired at assembly** because a subscription made as an import side effect is a subscription nobody
can find, and because that file is the only one that legitimately knows about two managers at once —
which is what the bus exists to keep out of the managers themselves.

**Cost.** Nothing survives a crash between publish and commit. For a household instance running one
process against one SQLite file, a durable queue would be machinery without a problem. When a
listener does I/O that can fail independently of the publisher — an email, a push, an index — that is
the moment to add persistence, and it will be an addition rather than a rewrite: the publisher's side
of the contract does not change.

---

## ADR-040 A step's ingredients are read out of its words, not tagged

**Status:** Accepted

**Context.** Cooking mode shows one step at a time (UC-9.3), and a cook standing at the hob needs the
quantities that step asks for without scrolling back to the ingredient list. Something has to say
which lines a step uses. The domain model has carried a note since Phase 1 that step-to-line
references "arrive with cooking mode" — this is that decision.

The obvious implementation is a join table, filled in by whoever authors the recipe.

**Decision.** `ExecutionEngine` derives the references by matching ingredient names against the
instruction text. Nothing is stored, and no author is asked.

The rule, in order:

1. The ingredient's **full name** appearing in the instruction is a reference.
2. Otherwise the **last word** of the name — "the flour", for *plain flour* — but only where exactly
   one line in this recipe answers to it.
3. Otherwise nothing.

Matching is case-insensitive, bounded by whole words, and tolerant of a trailing English plural.

**Rationale.** A tagged reference is a field nobody fills in. Recipes arrive here four ways
([V1](03-volatility-analysis.md#v1-recipe-provenance)) and three of them have no author present to
ask: an imported page carries no tags, a generated recipe would have to invent them, and the starter
set would need them written by hand. A feature that only works for hand-authored recipes is a feature
most of the collection does not have.

The names are already in the instruction. "Whisk the flour, baking powder, sugar and salt together"
names four of them in the words a cook would use, and reading that is exactly the kind of judgement
about steps that [V15](03-volatility-analysis.md#v15-execution-guidance) exists to encapsulate.

**Ambiguity resolves to nothing.** A recipe with plain flour and rye flour cannot say which one "the
flour" means, so it says neither. The failure to avoid here is not a missed reference — it is a
claimed one: a step pointing at an ingredient it does not use is a step a cook stops trusting, and
one wrong pairing costs more than ten absences. Same rule as an unclassified allergen
([ADR-006](#adr-006-allergen-determination-is-structural)) and an unreadable yield
([ADR-030](#adr-030-a-recipe-whose-yield-cannot-be-read-is-refused)).

**The engine returns positions, not content.** Everything it says about lines it says as an index
into the recipe's own list. That is what keeps measurement out of execution guidance: an engine that
hands back indices *cannot* scale, convert or round anything, so V4 stays in one place by
construction rather than by a rule somebody has to remember. The original sequence had
`ExecutionEngine` receiving an already-scaled recipe and a note saying it must never scale one; with
indices, the note is unnecessary.

**Cost.** It is a heuristic, and it is English-shaped. The head-word rule assumes a name whose last
word is its noun, and the plural tolerance assumes a trailing letter — a German compound
(*Weizenmehl* where the step says *Mehl*) matches nothing. Both degrade to showing no reference,
which is the safe direction, and both improve without a migration because nothing was stored.

An author who wants to be certain always has one lever: name the ingredient in full in the step.

---

## ADR-041 Work done the day before is lifted out only from the front

**Status:** Accepted

**Context.** A step marked *ahead* ([ADR-037](#adr-037-how-long-a-recipe-takes-is-two-numbers-both-derived))
happens without the cook — soaking beans, proving overnight, chilling dough. Cooking mode has to
surface it before the cook starts, or somebody begins dinner at six and discovers the beans wanted
starting yesterday.

The obvious implementation lifts every ahead step to the front as a "the day before" list.

**Decision.** Only the **leading run** is lifted. An ahead step anywhere else stays exactly where it
is in the method.

**Rationale.** You cannot chill dough you have not made. A shortbread that says *work the dough, chill
overnight, roll and bake* has its ahead step in the middle, and pulling it forward produces an order
nobody could follow — worse than not surfacing it, because it reads as instructions and is not.

The two cases are genuinely different facts. A leading ahead step is a **precondition**: do this
before you begin. A middle one is a **break**: the recipe spans two days, and the cook needs to know
where the seam is rather than to do it first. Cooking mode can offer "come back tomorrow" at a break;
it cannot offer anything sensible about a precondition it has scrambled into the method.

**Cost.** A recipe whose lead is written second — *cream the butter, but soak the beans the night
before* — does not get its lead surfaced. That is the author writing the steps out of order, and the
fix is to write them in order. Guessing which mid-recipe ahead steps were "really" preconditions
would be inventing an order the author did not write, in the one place where a wrong order is
actionable.

---

## ADR-042 A cooking session executes a planned meal

**Status:** Accepted

**Context.** Cooking mode has to end by consuming the stock the meal used (UC-9.6, FR-19). Stock is
held aside by a **plan slot** ([ADR-004](#adr-004-plans-reserve-stock-cooking-consumes-it),
[ADR-036](#adr-036-a-reservation-exists-only-while-it-is-held)), and `MealCooked` names one. So a
session has to relate to a slot somehow, and the question is whether it *requires* one.

The alternative is a free-standing session started from a recipe, which would need its own way to
work out what stock the meal used and its own way to spend it.

**Decision.** A session is opened for a plan slot. Cooking something unplanned means putting it on
today's plan first — one form the cook already has.

**Rationale.** **One record of a meal.** The plan is already where "what did we eat on Tuesday" is
answered, where a meal's guest list lives, and where its stock is held. A second place a meal can
exist would be a second history, and the two would disagree the first time somebody cooked without
planning.

**One consumption path.** A free-standing session would have to net its requirement against
availability at completion — a second implementation of the arithmetic `ReplenishmentEngine` already
does for planning, reached from a different manager. Two answers to "what did this meal take" is
exactly what [FR-7](02-requirements.md) exists to prevent for the shopping list, and the argument is
the same here.

**No polymorphic claim holder.** A reservation belongs to a plan slot and nothing else, which is what
lets `held_for_slot` and `consume_for_slot` be two lines each. Making the holder polymorphic to admit
a session would put a discriminator on the one table whose correctness ADR-004 turns on.

**Cooking without planning is one extra call, not a missing feature.** "Cook this now" is *plan it
for today, then cook it* — two actions that are each meaningful on their own, composed by the client,
which is the layer allowed to call two managers. The reservation happens in `PlanningManager`, where
the only implementation of it lives.

**Consequences for abandonment.** The original flow had `SessionAbandoned` releasing the meal's
reservation. With the claim owned by the slot that is wrong: giving up on cooking does not un-plan
Thursday's dinner, and releasing what it was holding would take it off the shopping list at the same
time. Abandoning closes the session and touches nothing else, so no second event is needed — the
distinction ADR-039 draws between a fact worth publishing and a state worth recording.

**Cost.** A cook who never plans meets the plan anyway. That is a real cost and it is bounded: the
slot they create is the record of what they cooked, which they wanted regardless. If it proves to be
friction, the fix is a button, not a second model.

**As built, the button exists.** `POST /cooking/sessions/for-recipe` is that button: it composes
`PlanManager.slot_for_now` and `CookingManager.start`, in the route, because a route is the one layer
allowed to reach two managers. The day is today and the meal is read off the clock by
`PlanningEngine.meal_at`; nobody is seated, so the recipe is cooked at the yield the cook was just
reading rather than quietly rescaled between one screen and the next. Both are editable on the plan.

The first version of it went straight to `PlanAccess` from `CookingManager` instead, and it looked
entirely correct: the session ran, the meal appeared on the plan, and it was marked cooked. It also
never touched the pantry, because stock is consumed against a **claim** and nothing had claimed any —
`place` is where provisioning happens, and skipping it skipped that. This is the ADR's "one
consumption path" argument arriving as a bug rather than as a paragraph. The test that names it is
`test_what_it_used_comes_out_of_the_pantry`.

---

## ADR-043 A page's method is edited on the way in

**Status:** Accepted

**Context.** A recipe imported from the web arrived with its instructions exactly as the site wrote
them. Checked against the pages this project tests against, that means:

- *"Gather all ingredients."* — a heading standing in for a step (Allrecipes)
- *"Cut 185g unsalted butter into small cubes and tip into a medium bowl. Break 185g dark chocolate
  into small pieces and drop into the bowl."* — two actions, one paragraph (BBC Good Food)
- *"They'll keep in an airtight container for a good two weeks."* — useful, and not something to walk
  a cook through at the hob
- *"Melt the butter (or a drizzle of oil if you want to be a bit healthier)…"* — an aside inside an
  instruction (Jamie Oliver)

A method written to be read on a sofa, imported into a screen a cook glances at with their hands
full. It is precisely the experience this product exists to replace, arriving through the front door.

**Decision.** Both readings — metadata and prose — go through one editing pass before the recipe is
stored. The pass splits a step that covers several moments, cuts what is not an instruction, says
each step in one or two plain sentences, and reports what the step asks of the cook.

**A step that waits ends at the wait.** "Pour in the batter and cook for two minutes" becomes two
steps, which is what lets the waiting carry a timer of its own (UC-9.4) and stops a cook holding a
pan while they read three more sentences.

**Rationale.** *One pass over both readings*, because "what does a cook actually do" is one question
and two implementations of it would drift apart at their own pace. It is also where the metadata path
gains something it never had: a duration and a temperature on the step they belong to, rather than
the page's single `cookTime` landing on the last one.

*The division of labour holds.* The model decides what a step **says**; a tested reader decides what
a number in it **means** — the same split that makes `read_ingredient` the one implementation of
"what does 225g mean". So `read_step_timing` is a pure function with a table of cases, and a range
takes its **lower** end: a timer that goes off at 25 minutes sends a cook to look at the oven, one
that goes off at 30 sends them to look at something already burnt.

*An improvement, not a requirement.* An instance with no model configured, one whose model is
unreachable, or one that answers with nothing keeps the steps exactly as the page wrote them. The
recipe still imports. A courtesy that can fail an import is not a courtesy.

**What must never be cut**, and what the prompt spends most of its words on: times, temperatures,
the quantities a step names, doneness cues, and warnings. A shorter method that lost *"stop just
before you feel you should, to avoid overmixing"* would be a worse import than the wordy one it
replaced. The live tests assert that particular sentence survives.

**Cost.** Three real ones.

*A second model call per import*, so importing is slower on an instance that has one. The
alternative was the complaint that prompted this.

*The recipe is no longer the page's words.* Provenance still records where it came from, but a cook
comparing the two will find them different. That is the point, and it is worth being honest that it
is a change and not a transcription.

*Calibration is a prompt, and prompts drift.* Getting here took three attempts: the first split at
every verb and turned a fifteen-step brownie into forty-two; the second was told to keep sentences
whole and stopped editing at all; the third dropped the articles and wrote telegrams. What settled
it was stating the two rules separately — split by moments, and write plain sentences — rather than
hoping one implied the other. The live tests exist so the next adjustment is measured rather than
guessed at.

---

## ADR-044 What a number in an ingredient line counts

**Status:** Accepted

**Context.** A cook imported a recipe and reported what came out. Three lines off one page:

| The page wrote | Quookly read |
| --- | --- |
| `2 ounces chicken fat ((taken from the cavity of the chicken))` | an ingredient called *"chicken fat ((taken from the cavity of the chicken))"* |
| `1 teaspoon neutral oil ((such as vegetable, canola, or avocado oil))` | *"neutral oil ((such as vegetable"*, note *"canola, or avocado oil))"* |
| `4 cloves garlic` | four of something called *"cloves garlic"* |
| `4-inch piece ginger` | **four** gingers |

The doubled brackets are the site's own; several large publishers emit them. The note was cut
in half because the reader looked for a comma before it looked for a bracket, and a
bracketed note nearly always contains one.

**Decision.** Three rules, all in the reader rather than in a model:

**A bracket is a note.** Taken out before commas are considered. Doubled and mismatched
pairs are collapsed first — `((… ) )` is what one page publishes, and a reader that insisted
on balance would put the whole apology in the ingredient's name.

**A counting word is not the ingredient.** "Cloves", "slices", "sprigs", "rashers" and their
German and French equivalents count *pieces of* something, and the something is the
ingredient. The word is kept as the line's note.

**A length is not a count.** "4-inch piece ginger" is one piece four inches long. The recipe
does not say what that weighs, so the amount stays **absent** and the length becomes the
note.

**Rationale.** The first two are not really about quantities at all — they are about the
**name**, and a wrong name is the more expensive failure. An unread quantity leaves a visible
gap a cook fills in a second. *"cloves garlic"* resolves against no registry, so importing
one recipe records a new ingredient nobody has heard of and nobody has classified for
allergens ([ADR-029](#adr-029-an-ingredient-the-registry-does-not-know-is-recorded-and-reported),
[ADR-006](#adr-006-allergen-determination-is-structural)). The recipe looks complete and is
quietly less safe.

The third is the ordinary rule of this codebase applied to a case that was getting it wrong:
four pieces of ginger is nine times the recipe, and **a wrong number is worse than a visible
gap because a cook cannot see that it is wrong.**

**In the reader rather than in a model**, even though a model would also manage it. These are
deterministic shapes, so they can be a table of cases; they cost no round trip; and they work
on an instance with no model configured, which is the instance importing from a site that
publishes its recipes properly. The division stays where
[ADR-043](#adr-043-a-pages-method-is-edited-on-the-way-in) put it: a model decides what a
line *says*, a tested reader decides what a number in it *means*.

**Cost.** Three word lists to keep — counting words, elisions, length measures — each of
which is a place a language Quookly does not yet read will be missing from. They fail the
safe way: an unrecognised counting word leaves the line as it was, which is where this
started, rather than producing something worse.

The lists are also a judgement that will be wrong somewhere. "Bar" counts chocolate and
measures pressure; "head" counts lettuce and is part of a fish. Both readings are recorded in
the note, so nothing is lost — but the *name* is now the reader's opinion rather than the
page's words, which is a change worth being honest about.

---

## ADR-045 Composition data is tried in a configured order, nearest table first

**Status:** Accepted. Amends [ADR-007](#adr-007-nutrition-data-usda-fooddata-central-as-the-base).

**Context.** ADR-007 chose USDA FoodData Central as the base and regional tables as *overlays*,
reasoning that "nutrient values for generic ingredients — flour, butter, chicken thigh — travel well
across borders".

That reasoning is wrong, and the way it is wrong matters.

**Composition data is not a fact about an ingredient. It is a measurement of a particular food
supply.** US wheat flour is fortified with folic acid and iron by law; Swiss flour is not. US milk is
vitamin-D fortified; Swiss milk is not. Fat standards for dairy, extraction rates for flour, and
breed and feed for meat all differ by country. Reading an American table for a Swiss kitchen does not
produce a value that is slightly off — for iron in white flour it produces a value for a food that is
not on sale here.

**Decision.** Sources are tried in an **ordered list**, and the first that has an ingredient answers
for it. The order is instance configuration (`QUOOKLY_NUTRITION_SOURCES`), shipped as:

    swiss, ciqual, cofid, usda

Every profile is stored per source, and the choice is made at read time. Changing the order is a
setting, not a re-import.

**One table answers for one ingredient, whole.** Nutrients are never taken from two at once: a value
with its protein from Bern and its fibre from Beltsville is a number nobody measured, and it would
have to be attributed to both.

**Rationale.** *Ordered rather than base-plus-overlay* because there are more than two tables and the
question "which do I believe" has one answer per ingredient, not one answer per application. A
cascade also states the fallback honestly: the Swiss database is about 1,200 generic foods and USDA is
thousands, so the table that is better where it applies goes first and the table that answers for
anything goes last.

*Configurable rather than derived from locale.* Deriving it would be defensible and would give a
Swiss instance the same order. It was rejected because the order is a judgement about **data quality
and relevance**, and an operator is better placed to make it than a locale string is — someone
cooking Thai food in Zürich may want a different order from their neighbour. The shipped default
carries the opinion; the setting means nobody is stuck with it.

*A name nobody recognises is skipped, not fatal.* A typo in a setting should cost an instance one
table, not its ability to start.

**What this changes from ADR-007.** USDA is no longer "the base"; it is the last resort. Its licensing
argument still stands and is why it stays in the list at all — CC0 is the only status with no
obligations, and it answers for ingredients no European table carries. What it is not is the right
first answer for the kitchens this product was built for.

**Consequences.**

*Coverage is visibly incomplete, and that is reported rather than hidden.* Of the 29 seeded
ingredients, the Swiss table answers for 26. Baking powder, bicarbonate of soda and wholemeal wheat
flour are simply not in it. A recipe using one of those reports its totals as **at least** that much
and **names the ingredient** — "two ingredients missing" tells a cook nothing they can act on.

*Portion weights are the one number no table publishes.* Every source gives figures per 100 g, and a
recipe says "2 eggs". Bridging that needs what one egg weighs, which the Swiss database does not
carry and which this project will not invent — eggs come in four sizes. `piece_grams` is therefore a
registry field that ships unset, and an egg goes uncounted until somebody fills it in. That is the
same rule as an unclassified allergen or an unreadable yield: absence does not get to read as a value.

*Attribution is per source and mandatory.* The Swiss grant is "Open use. Must provide the source", so
each table that answered is credited on the recipe (FR-20). A recipe drawing on two tables owes two
credits, which is why the credit is carried per profile rather than as one line at the bottom of the
application.

**Cost.** A mapping from this instance's slugs to published rows, written by hand and kept by hand.
That is deliberate: the Swiss table has four wheat flours by ash content, and choosing which one is
"plain flour" is a judgement somebody should make on purpose rather than a name match. Each mapping
records the row it came from, so any number on a screen can be traced to a published one.

---

## ADR-046 A suggestion earns its place by saving something

**Status:** Accepted

**Context.** "What should I cook this week" is the question Phase 6 exists to answer, and any
ordering answers it somehow. The obvious ordering is by how much of a recipe is already in the
cupboard. That is the wrong first question.

**Decision.** Recipes are ordered by four things, most important first:

1. **Whether the household can eat it.** Anything somebody cannot eat goes last.
2. **What the cook asked**, where they asked anything. A search is a question and it gets answered.
3. **What it saves** — each ingredient about to go off outweighs any amount of convenience, and
   coverage of the cupboard breaks the remaining ties.
4. **The recipe's own id**, purely as a tiebreak.

Every suggestion carries its **reasons**, and what needs eating is **named** rather than counted.

**Rationale.** A full cupboard gives a cook plenty of options. The spinach going off on Thursday is
the one thing that costs money if it is ignored — reducing that waste is a founding goal of this
product, so it is what the ordering optimises. Convenience is a tiebreak, not the objective.

**Coverage is a proportion, not a count**, so a large recipe is not punished for being large. Ten
ingredients of twelve is a better answer than two of two, which is a cup of tea.

**Nothing is hidden.** A dish somebody at the table cannot eat is ranked last and says so. Leaving it
out would be the interface making a decision about an allergy on the cook's behalf, which is what
[ADR-010](#adr-010-the-frontend-never-decides-suitability) forbids — and a cook may well be cooking
for themselves tonight.

**The reasons are not decoration.** A ranked list that only reordered itself would be asking to be
trusted rather than earning it. "Uses something up — caster sugar, plain flour" is checkable at a
glance; "2 ingredients need eating" is not, and a cook cannot act on it.

**Ordering is explicit, not automatic.** The list opens alphabetically. A cook who came to find a
recipe they already have in mind wants the alphabet, and a list that quietly rearranges itself around
the spinach is one they cannot learn the shape of. *Worth cooking* is one tap away and says what it is.

### The index behind it

Retrieval is separate from ranking — [V10](03-volatility-analysis.md#v10-discovery) splits them
because the index technology and the ranking policy change for different reasons at different rates.
Two decisions about the index are worth recording.

**It is rebuilt, not migrated.** The index is derived from the recipes, so it is not a source of
truth and is not treated as one: the whole thing is rebuilt at start-up in three queries. That means a
change to *what* is indexed needs no migration, no version marker, and has no way to be half-applied —
and an index that somehow fell behind heals itself rather than needing a repair tool.

**Recipes are indexed where they are stored,** in `RecipeAccess.store`, not by each caller. Four paths
store a recipe — authored, imported from a document, imported from a page, seeded — and "remember to
index it too" is precisely the shape of mistake that already cost the starter recipes their `serves`
once ([ADR-012](#adr-012-export-format-is-the-import-format)). A recipe imported at ten
o'clock should be findable at one minute past.

**Cost.** The ranking weights are a judgement with numbers in it, and numbers in a judgement invite
tuning by feel. They are kept as named constants with the reasoning attached, and the engine is pure,
so a change of policy is a change to a table of cases rather than an experiment in production.

Search is SQLite FTS5, which [ADR-009](#adr-009-sqlite-only-to-begin-with) already named as the place
the SQLite decision will strain first. It is a virtual table, so alembic can neither generate it nor
be allowed to see it — both the migration and the model metadata declare it, and autogenerate is told
to leave it alone. Without that last part every future migration would offer to drop the search index.

---

## ADR-047 A generated recipe is refused, not warned about

**Status:** Accepted

**Context.** A cook can ask for a recipe that does not exist (UC-1.4, UC-1.5). The household's
constraints go into the prompt, and the answer is then judged by `SuitabilityEngine` against its
*resolved* ingredients — a model asserting "this is dairy-free" carries no weight
([ADR-006](#adr-006-allergen-determination-is-structural)). The question is what to do when the
verdict comes back badly.

An imported recipe with a problem is **stored and marked**: it exists in the world whatever it
contains, and hiding it would be the interface deciding something about an allergy on a cook's behalf
([ADR-010](#adr-010-the-frontend-never-decides-suitability)).

**Decision.** A *generated* one is **refused with its verdict, and not stored**.

**Rationale.** The difference is who asked. An imported recipe is a thing the cook went and found; a
generated one was written on these people's behalf, in response to a request that named them. Handing
back something they cannot eat is a failure of the request, not a fact about a recipe — and putting it
in their collection with a red badge would be answering "make me dinner" with "here is one that will
hurt Mira".

The refusal carries the verdict, because "no" without a reason is not an answer. *Mira — parmesan* is
something a cook can act on: ask again, or reconsider the constraint.

**It is not a hypothetical.** On the first live run against a real model, told plainly that a recipe
must not contain milk, it wrote one with parmesan in it. The prompt changes the odds; the verdict is
the guarantee. That is exactly the split
[UC-1.4's flow](05-use-case-flows.md#uc-14-generate-a-recipe-from-pantry-stock) was drawn to make.

**Cost.** A cook can be refused twice in a row and have nothing to show for the waiting. That is the
right trade — but it is why the ask is retried on a *decoding* failure and not on a suitability one:
one is a model losing its place, the other is a model being wrong about food.

### What made generation work at all

Two settings, both discovered by running it rather than by reasoning about it.

**The shape is bounded.** `RECIPE_SHAPE` grew `maxItems` on its arrays and `maxLength` on its strings.
Reading a page is bounded by the page; *writing* one is bounded by nothing, and an open-ended array is
an invitation to a decoder to keep filling it. Asked to invent a recipe, this model looped to the
token limit **four times in five** until the arrays had an end — and still sometimes until the strings
did.

**The budget is small on purpose.** 2500 tokens, against a real recipe's ~500. It is not really a
budget: it is how long a loop is allowed to run before it is called one. At twelve thousand a runaway
answer costs forty seconds before anybody finds out; here, a few — and then it asks again.

Generation is also the one place a model is asked for something other than determinism. Extraction is
deterministic because the same page should yield the same recipe twice; a cook who asks twice for "a
quick pasta" and is handed the identical answer has been given a lookup table. That is also what makes
the retry work: the same question asked again is genuinely a different attempt.

### Adapting one (UC-1.7)

A **version** of a recipe — dairy-free, without the eggs, olive oil instead of butter — is the same
sequence with one thing added and one changed. The original goes into the asking, **as words rather
than as a data structure**: a model adapts a recipe better when it is reading a recipe, and the answer
comes back in the shape so the question does not have to.

What comes back records which recipe it came from (`derived_from`) and carries `provenance = derived`
rather than `generated`. The histories differ and V1 exists to record that: one was invented from
nothing, and this one started from something the cook already had. A cook looking at a dairy-free
shortbread should be one tap from the shortbread.

The refusal rule is the same one, and this is where it bites hardest: somebody asking for a
*dairy-free* version and being handed one with cream in it is precisely the case it was written for.

Scaling is deliberately **not** part of this. UC-1.7 lists it alongside substitution, but a recipe
already scales to any yield through `MeasureEngine` (UC-2.1) — asking a model to multiply is asking it
to do arithmetic, which is the one thing this codebase never asks of one.

**The exchange format goes to 4** for the new provenance value. This is the one bump that is not about
a missing field: an older build reading `"provenance": "derived"` would refuse the whole document over
one recipe, with a validation error rather than an explanation. The version check says why first. The
`derived_from` link itself does not travel — a recipe id belongs to the instance that issued it, and a
document is a set of recipes rather than a graph.

## ADR-048 A ticked shopping line remembers what it was ticked at

**Status:** Accepted

**Context.** The shopping list is derived: it is what the plan could not reserve, recomputed on every
read. A tick is the one piece of state a cook adds to it by hand, and the plan underneath keeps
moving — a meal added on Wednesday changes what Monday's list asks for.

So a tick has to survive being recomputed, and the question is what it means afterwards.

**Decision.** A tick stores the plan, the ingredient, **and the quantity it was ticked at**. A line
reads as bought only while the list still asks for exactly that much. Otherwise it comes back
unticked.

**Rationale.** The failure the naive version produces is silent and expensive. A cook ticks off 200 g
of flour, plans a second night of pancakes, and the list now needs 400 g — with the tick carried
across, flour reads as bought and they go home with half of what they need, having *looked* at the
list. The one thing a shopping list must never do is confidently show a line as handled when it is
not.

It is the same rule as everywhere else here: **absence is never zero**, and a stale yes is worse than
a no, because a no sends somebody to the shelf and a stale yes sends them past it. Storing the
quantity is one column and one comparison; the alternative is a class of bug that only shows up in a
kitchen.

Ticking down is treated the same way, though it is the harmless direction: what was ticked answered a
different question, so it is asked again.

**Why the tick is on the server.** Shopping is the one thing in Quookly two people do at once — one in
the shop, one at home adding to the list. A tick in a browser would be invisible to the other, and
invisible to the same person on a second device. The screen still marks the line before the answer
comes back, because a shop is where signal is worst and a checkbox that waits for a round trip reads
as broken.

**Cost.** A tick does not survive a change to the quantity, which will occasionally annoy a cook who
bought the larger bag anyway. That is the direction the error should fall in, and unticking is one
tap.

## ADR-049 An account is applied for, and an administrator answers

**Status:** Accepted

**Context.** Quookly had a sign-in page and no way to get an account. The API had open
registration; nothing in the interface reached it, which is the worst of both — a visitor sees a
locked door, and anybody who reads the source finds it unlocked.

Three ways to fix that, and the instance being *self-hosted* decides between them.

**Rejected: open registration.** A Quookly instance is somebody's household server, running on their
hardware, holding their family's dietary constraints. A stranger creating an account on it is not a
sign-up, it is a person in the house.

**Rejected: invitation only.** Correct, and unfriendly. A visitor who arrives at a friend's instance
has nowhere to go and nothing to do but ask out of band. The instance cannot say "not you" without
also saying "not anybody", and a self-hosted product that cannot welcome anybody is a product with
one user.

**Decision.** Anybody may **apply**. An administrator approves or refuses. An account carries a
`Standing` — `APPLIED`, `APPROVED`, `REFUSED` — and only an approved one can sign in.

**Rationale.** The door has a bell. A visitor can act, an owner decides, and neither has to leave the
app to arrange it.

**Three states, not a boolean.** *Nobody has looked yet* and *somebody looked and said no* are
different facts, and the applicant is owed a different sentence for each. A boolean would tell
somebody who was refused to keep waiting.

**`APPLIED` is the default** on the column and in `CookAccess.register`. A code path that forgets to
state a standing leaves somebody locked out, which they can report and an admin can fix; the opposite
default lets a stranger in silently. Where the two errors are not equally bad, the default belongs on
the recoverable side.

**Standing is revealed only after the password matches.** Sign-in answers `401` with one message for
a missing account and a wrong password, exactly as before — anything else is a way to ask which
addresses have applied here. Once the password *has* matched, saying "you are waiting" or "you were
declined" tells the asker nothing they could not already establish, and saying nothing instead leaves
an applicant retyping a password that was right all along. The refusal is `403`, not `401`: the
credentials were right, retrying changes nothing, and a client that read it as "sign in again" would
loop.

**The password is taken at application time** and kept hashed, rather than asked for again on
approval. Being let in should be a message to read, not a second form to fill in.

**Approval seeds a kitchen**, for the same reason bootstrap does (UC-10.4): an empty app is
indistinguishable from a broken one.

**Cost.** An administrator has to answer the bell, and nothing notifies them yet — the queue is a
screen they visit. Email is a dependency a self-hosted instance should not need to work, so a
notification channel is a later decision rather than a hidden requirement of this one. A refusal is
also reversible on purpose, because an admin who mis-clicks should not have to reach for a database.

## ADR-050 The shipped registry is derived from a published table, and says when it does not know

**Status:** Accepted

**Context.** Quookly shipped twenty-nine ingredients. Everything else a cook typed resolved to
nothing, so importing an ordinary recipe invented entries nobody had classified: no density, no
allergens, no nutrition, and a fresh one per spelling. A registry that small is not a registry — it
is a list of the things the starter recipes happen to use.

The Swiss Food Composition Database publishes 1,216 generic foods with the nutrients an EU label
declares, and the same database in German, French and Italian with **identical row ids**.

**Decision.** Derive the registry from it. `seed/generic.py` reads all three editions we ship and
builds `seed/generic-foods.json`: roughly nine hundred entries, each with names in three languages,
a kind, a density where published, the nutrition from the same row, and an allergen answer that may
be *no answer*.

**Rationale for deriving rather than curating.** Nine hundred hand-written entries is not work
anybody would finish, and the judgement that matters is not per-row — it is in the rules. The rules
are in one file, tested, and re-runnable when the FSVO publishes an edition.

**What is left out, and why.** Prepared dishes. A registry is the list of things a recipe *line* can
name, and "Lasagne, homemade" is a recipe. Cooked variants of a food that also appears raw go too: a
line says "carrot", and eight carrots in a picker is worse than one.

**The allergen rule is asymmetric, on purpose.** Saying an ingredient *contains* something can only
make a verdict more cautious — a wrong "contains" costs a cook a dish. Saying it contains *nothing*
can put an allergen on a plate. So a keyword is enough to **add** an allergen, and only a category
whose complete set is knowable from the category alone may be declared **complete**
([ADR-006](#adr-006-allergen-determination-is-structural)). Sausages, sauces, breads and anything
whose name says it was composed come back unclassified, which reads as "nobody has looked". Roughly
four hundred entries are answered completely and five hundred are not, and that ratio is the honest
one rather than a shortfall.

Two guards earn their place. A hard cheese named *Sbrinz* or *Tête de Moine* contains no word a name
table could match, so **the category answers for it** — twenty entries are in that position, and a
registry judging on names alone would have handed every one of them to somebody avoiding dairy. And
a *game terrine* is filed under "Meat and offal/Game": the first version declared it allergen-free,
which is exactly the direction that must never happen.

**A name means one ingredient per language**, enforced by a unique index. The builder settles every
claim at build time rather than letting the loser vanish silently at seed time, and the hand-written
starter set wins every collision — somebody chose which of four wheat flours answers for "plain
flour", and it carries a density and a piece weight this table does not publish.

**Cost.** Three workbooks, two megabytes, in `reference/`. A 550 KB seed file. About two seconds of a
fresh instance's first start-up, and two more on each one after it while the published figures are
restated — which is why `register_many` and `record_profiles` exist: one transaction rather than nine
hundred. And the table's vocabulary is Swiss-English, so *zucchini*, *eggplant*, *shrimp* and
*yogurt* need British spellings taught by hand, keyed by row id like every other judgement about this
document.

**What it does not fix.** The table has eleven spices and no bay leaf, chilli, oregano or vanilla. A
cook will still create entries, and Phase 7 owes them a screen to see and correct what they and the
importer have made.

## ADR-051 Whether an entry has been reviewed is a different column from whether it has been classified

**Status:** Accepted

**Context.** Importing a recipe creates registry entries. It has to: a line that resolves to nothing
cannot be shopped for, scaled or judged, so `RecipeManager` invents one
([ADR-029](#adr-029-an-ingredient-the-registry-does-not-know-is-recorded-and-reported)). What it
invents is a guess — `kind` assumed `SOLID`, no density, and allergens deliberately left
*unclassified* because nobody has looked
([ADR-006](#adr-006-allergen-determination-is-structural)).

Phase 7 made the registry browsable, and the obvious next question was how an administrator finds the
entries that need a second look. Two candidates already existed on the row, and neither answers it.

**Rejected: read it off `allergens_classified`.** It looks like the same question and is not. Against
the registry this instance actually ships, **486 of 893 seeded entries are unclassified** — the Swiss
table ([ADR-050](#adr-050-the-shipped-registry-is-derived-from-a-published-table-and-says-when-it-does-not-know))
simply could not answer for them. Those rows are exactly as a published source left them and need no
review at all. Filtering on that flag buries the handful an import invented under four hundred that
are fine, which is the same as having no filter.

**Rejected: read it off `origin`.** Closer — everything an import invents is `Origin.USER` — but it
stops working the moment it is used. An approved entry stays the cook's own for ever, because an
upgrade must never replace it ([ADR-016](#adr-016-ship-seed-content-marked-and-upgradable)). So
provenance cannot distinguish *reviewed* from *not yet*, and an admin who cleared the queue would
find it still full.

**Decision.** A separate `approved` boolean on the registry entry. A seeded row arrives approved;
anything else arrives unapproved and is **usable immediately**. Approving records the review and
nothing else: it does not classify allergens, and it does not change the origin.

**Rationale.** The two flags answer different questions about different subjects.
`allergens_classified` is a fact about **the ingredient**: has anybody established what is inside it.
`approved` is a fact about **the entry**: has anybody looked at what this row claims to be. An
administrator can perfectly well approve "crème fraîche is a solid with no density recorded" as a
faithful description of what is known, without having said one word about whether it contains milk.
Folding those into one flag would let a review be read as a classification, and a classification is
the thing ADR-006 says must never be inferred.

**Unapproved does not mean unusable.** Refusing to complete an import until an administrator wakes up
would make the feature useless, and the guesses are already conservative in the direction that
matters: an unclassified allergen never claims a recipe is safe. The flag exists to get somebody's
attention, not to withhold anything.

**The migration backfills from provenance**, which is the only evidence it has: `SEED` becomes
approved, everything else does not. The column default is `false` for the same reason ADR-049's is
`APPLIED` — if a code path forgets to state approval, the failure is a queue with too much in it,
which is visible and tedious. The opposite default marks an entry as looked at when nobody looked.

**What this does not settle.** Correcting an entry, and merging two that are the same food under
different names, are the operations that make review worth doing; they follow. Merging is the one
that matters, because an import that created `plain flour` beside a registry that already had
`wheat flour` has split one ingredient in two, and every allergen and nutrition fact now answers for
half a kitchen.


## ADR-052 Merging repoints an eater's constraints, which nothing in the database protects

**Status:** Accepted

**Context.** Two registry entries can be the same food. An import that created `plain flour` beside a
registry that already had `wheat flour` has split one ingredient in two, and every allergen and
nutrition fact then answers for half a kitchen. Phase 7 owes an admin the ability to put them back
together.

A registry entry is pointed at from seven tables by foreign key — nutrient profiles, names,
allergens, recipe lines, pantry lots, waste, shopping ticks — and from an eighth by **text**.
`EaterConstraintRow.ingredient_slug` is deliberately not a foreign key
([the domain model](06-domain-model.md) records why): somebody avoids coriander whether or not the
registry has heard of it, and a constraint that waits on a registry entry is a constraint that is
silently not applied.

**Decision.** `IngredientAccess.merge` is one transaction that repoints all eight, including the
constraints, and it is written as a single function rather than composed from smaller verbs.

**Rationale.** Seven of those relationships fail loudly if forgotten — a foreign key violation, or a
recipe line pointing at a row that is gone. The eighth fails **silently and in the dangerous
direction**: an eater who avoids `plain-flour` for medical reasons simply stops being warned, and
nothing anywhere reports it. There is no database constraint that can catch it and no test that
would fail by accident. It is called out in the docstring, has a test of its own, and is the reason
this is not five tidy little functions that a later refactor could reorder.

**Allergens are the union, and an examination on either side counts for both.** Two entries that
disagree are two examinations of one food; the merge takes the cautious reading, so it can add an
allergen and can never remove one ([ADR-006](#adr-006-allergen-determination-is-structural)). An
unexamined side adds no information — the food was examined, whichever row somebody wrote it on.

**The loser's names survive as spellings of the keeper.** That is the whole difference between
merging and deleting. A page that says "plain flour" has to keep resolving, or the next import
invents the duplicate again and the admin's work is undone by the next URL somebody pastes.

**The keeper's facts win, and its gaps are filled from the loser.** An admin merging *into* an entry
has chosen it as the truthful one, but a density on either side still describes the same food.

**Unique constraints decide what is dropped, not what fails.** Four of the repointed tables have
unique constraints that a naive repoint would violate — `(locale, normalised)` on names,
`(ingredient_id, allergen)`, `(ingredient_id, source, nutrient)`, `(plan_id, ingredient_id)` on
shopping ticks. In each case the keeper's row stands and the loser's duplicate is deleted, because
the keeper is the entry that was chosen.

**Cost.** Merging cannot be undone. The interface therefore asks twice and says plainly what moves.
An undo would mean recording the whole prior shape of eight tables, which is a bigger machine than
the mistake warrants at household scale.

**What this does not settle.** The survivor keeps the keeper's `origin`, so merging a cook's entry
into a seeded one produces a seeded row carrying names a cook contributed. If a future upgrade path
([ADR-016](#adr-016-ship-seed-content-marked-and-upgradable)) replaces seeded rows wholesale it must
not discard those aliases. Recorded here rather than solved, because the upgrade path is Phase 9 and
guessing at its shape now would be inventing a constraint for it.


## ADR-053 The matcher ranks; a person decides

**Status:** Accepted

**Context.** Two entries in the registry can be the same food under different names, and
[ADR-052](#adr-052-merging-repoints-an-eaters-constraints-which-nothing-in-the-database-protects)
gave an administrator a way to put them back together. Finding them by hand across nine hundred
entries is another matter. The obvious next step is a fuzzy matcher — and the obvious next step
after *that* is to use it during import, so a page saying `creme fraiche` resolves to the entry
already there instead of inventing a duplicate.

That second step is where the danger is. Today an ingredient the registry cannot resolve is recorded
and reported ([ADR-029](#adr-029-an-ingredient-the-registry-does-not-know-is-recorded-and-reported)),
which leaves the recipe reading *unknown* — conservative, and visible. A fuzzy match that is wrong
reads *known*, with another food's allergens attached, and nothing anywhere says so.

**Decision.** `MatchingEngine` returns **ranked candidates with a reason, and never a decision**. The
registry screen shows an administrator possible duplicates and they choose. An import may attach a
suspicion to the entry it creates; it still creates the entry, and never resolves a line to a
candidate.

Separately, and not part of this: accent folding in `IngredientAccess.resolve` *does* resolve, because
`crème` and `creme` are one word written two ways rather than two words that resemble each other. It
is exact, it is a fallback behind an exact match, and it refuses when ambiguous.

**Rationale.** The two failures are not symmetrical. A missed duplicate costs an administrator a
merge they have to find themselves; a wrong match costs somebody an allergic reaction. Where the
errors are that unequal, the machine gets the half it cannot get wrong.

**Every suggestion says why**, the same rule as [ADR-046](#adr-046-a-suggestion-earns-its-place-by-saving-something).
"The same words in a different order" is something a person can check at a glance; a confidence of
0.92 is not.

**What the engine learned from being measured.** The first version was written against intuition and
run against the shipped registry, where its highest-scoring duplicate was `condensed milk, sweetened`
against `condensed milk, unsweetened` at 0.98. Three rules came out of that, and each looks
unnecessary until it is not:

- **Numbers distinguish.** The first version dropped digits, reasoning they would swamp the
  comparison. Backwards: in this registry the number *is* the distinction — `at least 15% fidm
  appenzeller` and `at least 45% fidm appenzeller` are different cheeses.
- **Negation is invisible to character similarity.** `sweetened`/`unsweetened` and
  `drained`/`not drained` are near-identical as strings and opposite as foods. Checked explicitly,
  not scored lower.
- **Compare word by word, not character by character.** `peach with sweetener, canned, drained` and
  `pear with sweetener, canned, drained` scored 0.96 on the whole string. A long agreeing description
  must not outvote the word that differs.

**What it cannot do.** It finds names that are *written* alike. It cannot tell that `plain flour` and
`wheat flour` are one ingredient, because nothing about the strings says so — that is a question
about food, not about spelling. Widening the threshold until it caught such pairs would bury the real
ones; the honest answer is that semantic synonyms need a person or a model, and the review queue is
where a person already is.

**Cost.** The sweep is O(pairs) and takes a few seconds against nine hundred entries even with
blocking, so it is on demand rather than on page load. If it ever wants running regularly it belongs
in a CLI command and a cron job rather than inside the request that serves the page.


## ADR-054 `AcademyManager` is reinstated

**Status:** Accepted

**Context.** [The volatility analysis](03-volatility-analysis.md#what-is-deliberately-not-a-service)
rejected `AcademyManager` on the grounds that Academy content is merely authored and read, and that
the interesting part — a contribution earning recognition — is V11 and belongs to
`EngagementManager`.

That reasoning holds for the *interesting* part and fails for the rest, in exactly the way
[ADR-021](#adr-021-account-management-does-need-a-manager) failed for accounts. A Client may not call
Resource Access, so "authored and read" has no legal shape without a manager. And the sequence is not
empty: a cook asking what a term means may find nothing, in which case the answer is composed by a
model, stored, marked as unreviewed and returned — four steps across an engine and two resource
access services, which is a use case by any definition.

**Decision.** `AcademyManager` exists. It owns looking a term up, authoring and correcting an entry,
approving one, and asking for an explanation of a term nobody has explained.

**Rationale.** The test for promoting a rejected service is unchanged: *does it vary for its own
reasons, at its own rate?* The corpus of explanations grows when cooks meet words they do not know,
which has nothing to do with when recipes change or when the pantry is restocked.

Recognition still lives in `EngagementManager` and still waits for Phase 8. Moderation does not:
approving an entry is [ADR-051](#adr-051-whether-an-entry-has-been-reviewed-is-a-different-column-from-whether-it-has-been-classified)'s
shape exactly, and needs no scoring rules to work.

**Cost.** One more manager, and one more line in the independence contract that keeps managers from
calling each other. Both are the point: adding it is a line in a review rather than a silence.


## ADR-055 A step finds its techniques by the words it already uses

**Status:** Accepted

**Context.** UC-2.5 and UC-9.5 want an unfamiliar term in a recipe step to be something a cook can
look up — on the recipe page, and without losing their place while cooking. Something has to decide
which words in *"fold the whites into the batter"* are techniques.

[ADR-040](#adr-040-a-steps-ingredients-are-read-out-of-its-words-not-tagged) already settled the
same question for ingredients: read them out of the instruction's own words rather than asking
anybody to tag them. The same argument applies — nobody writing a recipe will tag its verbs, and an
imported one certainly has not.

The open question is how much variation the match should absorb. Written naively it goes wrong in
both directions: an exact match on "fold" misses *"folding"*, *"folded in"* and *"carefully fold"*,
while a fuzzy match on edit distance turns *"boil"* into *"broil"* and *"sear"* into *"shear"*.

**Decision.** **The fuzziness lives in the vocabulary, not in the match.** A technique stores the
ways people write it — a canonical term and its spellings and inflections, per locale, in the same
shape a registry entry stores its names. Spotting a technique in a step is then exact matching over
normalised, accent-folded tokens, longest term first.

**Rationale.** This puts the judgement somewhere a person can see and correct it. A wrong alias is a
row somebody can delete; a wrong similarity threshold is a number nobody can argue with. It is the
same reason the ingredient registry stores `cornstarch` beside `cornflour` rather than trying to
compute that they are the same word.

It is also the only version that is cheap enough to run everywhere it is wanted. Recipe pages and
cooking mode both need it, per step, on every read. A model call per step is out of the question and
a fuzzy comparison against every technique is O(steps x corpus) for an answer that would still be
wrong sometimes.

**Where the variants come from.** Seeded entries ship theirs. A cook adding an entry writes them.
And where a model is configured it proposes them **once, when the entry is created** — which is the
right place for a guess: a proposed alias is reviewed before it can ever match a step, rather than
being re-guessed on every page view.

**It returns positions, not content**, exactly as `ExecutionEngine` does for ingredient lines: an
engine handing back offsets cannot decide how a term is rendered, which keeps the decision in one
place.

**Where it lives.** `MatchingEngine` — it already owns "which written names mean the same thing",
this is the same job with the query and the corpus swapped, and it is already the pure engine that
neither reads a database nor decides anything.

**Cost, stated plainly.** A genuinely novel phrasing is missed until somebody adds it. That is a
miss, not a mistake: the step reads exactly as it does today, and nothing false is asserted. Given
the alternative is a spurious link from *"sear"* to *"shear"*, missing is the failure to prefer.


## ADR-056 A generated explanation is marked, unreviewed, and never an input to a judgement

**Status:** Accepted

**Context.** There is no openly available database of cooking techniques to derive an Academy from
the way [ADR-050](#adr-050-the-shipped-registry-is-derived-from-a-published-table-and-says-when-it-does-not-know)
derived the ingredient registry from a published table. The corpus has to come from three places: a
small hand-written seed, what cooks write, and what a model composes when somebody asks about a word
nobody here has explained.

The third is the one that needs rules. Cooking advice can be wrong in ways that matter — a
temperature for chicken, a time for preserving, a claim about what is safe to eat raw — and a
generated paragraph reads exactly as confidently as a checked one.

**Decision.** Three rules, and the third is the load-bearing one.

**Generated entries are marked as generated, and separately as unreviewed.** Two facts, two fields,
for the reason [ADR-051](#adr-051-whether-an-entry-has-been-reviewed-is-a-different-column-from-whether-it-has-been-classified)
gives: *who wrote this* and *has anybody checked it* are different questions, and a cook-written entry
nobody has read is not the same thing as a model-written one an administrator has approved.

**A seeded or cook-written entry is never replaced by a generated one.** Generation fills gaps only.
Where a technique carries a safety consequence, that is exactly where the hand-written seed should
be the thing that answers.

**Academy content is never an input to a judgement.** `SuitabilityEngine` and `NutritionEngine` must
not read it, and an import-linter contract says so — the same containment trick that keeps the ORM
inside the access layer. This is the rule that makes the other two survive contact: as long as an
explanation is only ever *shown to a person*, a wrong one is a bad paragraph. The moment anything
computes from it, a wrong one is a wrong verdict, and
[ADR-006](#adr-006-allergen-determination-is-structural) says where that ends.

**Rationale.** The instance may have no model at all — the inference provider is configured by
environment and reported by the app
([ADR-033](#adr-033-the-inference-provider-is-configured-by-environment-and-reported-by-the-app)) —
so generation is an enhancement to a working Academy, never its foundation. An instance with no
provider has the seed and whatever its cooks have written, and every screen works.

**Cost.** An instance that leans on generation accumulates unreviewed paragraphs, and the queue of
things to approve grows in a way the registry's never did, because nobody has to look up an
ingredient for it to exist. Accepted: the alternative is refusing to answer a cook who asked what
*deglaze* means, and the marking is what keeps an unchecked answer honest about being one.


## ADR-057 The Academy is sections of pages, not a table of techniques

**Status:** Accepted — revises the shape assumed by
[ADR-054](#adr-054-academymanager-is-reinstated) and
[ADR-055](#adr-055-a-step-finds-its-techniques-by-the-words-it-already-uses), which both stand
otherwise.

**Context.** The Academy was designed around a `Technique`: a word a cook might not know, and what it
means. Fifty were written. Two things about that shape were wrong before any of it was built.

The first surfaced while writing the seed. `curdle` is not something you do, it is something that
happens to you, and `al dente` is a doneness. Both are words a cook meets and wants explained, and
neither is a technique. A table named for one kind of thing collects a second kind by accident and
then has nowhere to put the third.

The second is that the ingredient registry already owes an Academy page — *what an ingredient is,
what it is called elsewhere, what it weighs, what it contains, what it can be swapped for*. That was
written down as a Phase 7 obligation long before this, and it is plainly not a technique.

**Decision.** An Academy **page** is the unit, and it carries a **kind** — `technique`, `ingredient`,
and whatever follows. The sections are how it is browsed; the page is what is stored, edited and
linked to.

**An administrator edits a page**: its text and its translations, and the pictures on it. Which pulls
`MediaAccess` forward out of Phase 8, because a page about julienne without a photograph of julienne
is a page explaining a knife cut in words.

**An ingredient page sits over the registry rather than duplicating it.** The registry holds the
facts — kind, density, allergens, published figures — because those are computed on. The page holds
the prose and the pictures, and names the registry entry it is about. Nothing is stored twice, and
the containment in [ADR-056](#adr-056-a-generated-explanation-is-marked-unreviewed-and-never-an-input-to-a-judgement)
survives intact: what an engine reads still comes from the registry, and what a person reads comes
from the page.

**Rationale.** The volatility was never "techniques". [V18](03-volatility-analysis.md#v18-explanation)
asks *what does a cook do when they meet a word they do not know*, and the answer has never been
restricted to verbs. Naming the entity after the first section we happened to write would have made
the second one a migration.

**Cost.** A page with a kind is less specific than a technique, so what a page *has* varies by kind —
an ingredient page names a registry entry and a technique page does not. That is a nullable column
and a branch in one renderer, which is cheaper than a second table that shares nine tenths of its
columns.


## ADR-058 Ambiguity is shown where a person resolves it, and refused where something computes on it

**Status:** Accepted — supersedes the "a term means one technique per language" rule in
[ADR-055](#adr-055-a-step-finds-its-techniques-by-the-words-it-already-uses).

**Context.** ADR-055 gave Academy terms the same unique index a registry name has: one term, one
entry, per language, refusing the second claim. That was copied from the registry without asking
whether the reason carried over.

It does not. The registry refuses ambiguity because a recipe line resolving to the wrong ingredient
gets the wrong food's allergens
([ADR-006](#adr-006-allergen-determination-is-structural),
[ADR-029](#adr-029-an-ingredient-the-registry-does-not-know-is-recorded-and-reported)) — and the
accent-folding fallback refuses for the same reason. Nothing computes on an Academy page. A cook who
lands on the wrong explanation reads a paragraph about the wrong thing and clicks again.

And the collisions are not hypothetical. `grill` in British English is heat from above and in Swiss
usage is a fire outdoors; `glacé` is iced as readily as glazed; an ingredient section will want
`butter` for a food while a technique section wants it for mounting a sauce.

**Decision.** Two rules, and which applies is decided by what happens next.

**Where something computes on the answer, ambiguity is refused.** Unchanged: `IngredientAccess`
resolves one name to one entry or to nothing.

**Where a person resolves it, ambiguity is shown.** Several Academy pages may claim a term in a
language. A page whose term is shared carries a **hatnote** at the top listing the others, the way an
encyclopedia does. And a step's word links to the **term**, not to a page: one claimant opens the
page, several offer a chooser. Nothing picks arbitrarily and nothing is stored to go stale, because
the set of claimants is a query.

**Rationale.** The unique index was solving a problem the Academy does not have, at the cost of
refusing entries a cook legitimately wants. Under it, adding an ingredient page for butter would have
been rejected because a technique page already said *beurre monté*.

Stated as one principle rather than two exceptions, because it is the same judgement made throughout
this codebase: an unconfirmed match must not read as a confirmed one *when something acts on it*.
When a person acts on it, showing them the choice is the confirmation.

**Cost.** A term with many claimants makes a chooser nobody enjoys. That is a signal to write a
better term or merge two pages, and it is visible — which a silently-refused second entry never was.


## ADR-059 A step may name its own links, and a recipe may be edited

**Status:** Accepted — extends [ADR-040](#adr-040-a-steps-ingredients-are-read-out-of-its-words-not-tagged),
which stands.

**Context.** ADR-040 settled that a step's ingredients are read out of its own words rather than
tagged, because nobody writing a recipe will tag it and an imported one certainly has not.
[ADR-055](#adr-055-a-step-finds-its-techniques-by-the-words-it-already-uses) extends the same
automatic reading to Academy terms.

Automatic reading is right as the default and wrong as the only option. It cannot know which flour
*"the flour"* means when a recipe uses two, and where a term has several claimants
([ADR-058](#adr-058-ambiguity-is-shown-where-a-person-resolves-it-and-refused-where-something-computes-on-it))
it can only offer a chooser. Somebody who knows the answer has no way to record it.

They also have no way to record anything else. **A recipe in this application can be created and
never edited.** There is no `PUT`, no `PATCH` and no `DELETE` on a recipe — a typo in an imported
recipe is permanent, a misread quantity is permanent, and a bad import can only be lived with. That
is a hole independent of anything the Academy wants.

**Decision.** Recipes become editable, and an instruction may carry an explicit link.

The syntax is `[[slug]]`, or `[[slug|the words as written]]` where the link text differs from the
slug. It resolves against Academy pages, and because an ingredient page names its registry entry
([ADR-057](#adr-057-the-academy-is-sections-of-pages-not-a-table-of-techniques)) one namespace covers
both — `Sift the [[plain-flour|flour]] into the bowl` says which flour.

**An explicit link wins over automatic spotting for the words it covers**, and the rest of the step
is read automatically as before.

**Only a person may write one.** A model composing an instruction never emits this syntax, and it is
stripped from model output if it does. A model that could write a link would be deciding one, which
is exactly what [ADR-053](#adr-053-the-matcher-ranks-a-person-decides) says it must not do.

**Two texts, and which one each caller gets.** The stored instruction keeps the markup; a reader is
sent the resolved text with the brackets gone, because the brackets are not on screen. Marks are
therefore positioned into the *resolved* text, not the stored one — a step comes back as
`instruction` (what a cook reads, which the marks index into) alongside `written` (what is stored,
which is what an edit form must be filled from). Filling a form from the resolved text would delete
the author's link the moment somebody corrected a typo in the same sentence, which is precisely the
failure this decision exists to prevent.

**Rationale for markup over an offsets table.** Offsets break the moment somebody edits the sentence
they point into, which is the one thing an editable recipe guarantees will happen. Markup travels
with the words it marks.

It also degrades well. The interchange format
([ADR-012](#adr-012-export-format-is-the-import-format)) carries the instruction as written, so a
reader that does not know the syntax shows `[[plain-flour|flour]]` — legible, ugly, and lossless.
An offsets table would either be dropped or silently misapplied.

**Cost, and an open question this forces.** Editing a recipe makes
[recipe versioning](06-domain-model.md#open-questions) pressing rather than theoretical: a plan
references a recipe, and a cooked meal referenced it at the time. The first cut edits in place and
keeps no history, which is the honest simple answer and not obviously the right one. A session
already in progress is insulated by accident rather than by design — cooking mode keeps the meal as
the server last described it, so a mid-session edit does not move under the cook's hands.
