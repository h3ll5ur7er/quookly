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

**Status:** Proposed — confirm before the pantry schema is written

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

**Confirm:** that "deduction on planning" meant "do not let me plan two meals with the same
ingredient", which reservation delivers, rather than literal immediate removal.

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

**Cost.** Every ingredient must resolve to a registry entry before suitability can be judged; an
unresolved ingredient must be treated as *unknown*, not as *safe*. Unknown must surface as a warning
in the UI, never be silently omitted.

---

## ADR-007 Nutrition source is pluggable and unresolved

**Status:** Open

**Context.** Nutrition requires reference data. Options include a bundled public dataset, per-
ingredient user entry, and model estimation.

**Decision so far.** `IngredientAccess` exposes `nutrients_for`, and `NutritionEngine` consumes what
it is given. Profiles carry a confidence level. The actual source is deferred.

**Open.** Which dataset, under which licence, and whether it can be redistributed inside a
self-hosted container. Swiss and UK sources are both relevant given the target locales. **Licensing
must be verified before any dataset is vendored** — this has not been done.

---

## ADR-008 Enforce the call rules with import-linter

**Status:** Proposed

**Context.** The call rules are currently prose. Prose is not enforcement, and layering rules decay
under deadline pressure.

**Decision.** Add `import-linter` to the backend with a layered contract, and run it as part of
`just backend check`.

**Rationale.** NFR-10 requires conformance to be a build failure rather than a review comment. The
template already anticipates this — `just backend clean` removes `.import_linter_cache`, though the
tool was never added.

**Sketch:**

```toml
[tool.importlinter]
root_package = "quookly"

[[tool.importlinter.contracts]]
name = "iDesign layers"
type = "layers"
layers = ["quookly.routes", "quookly.managers", "quookly.engines", "quookly.access"]

[[tool.importlinter.contracts]]
name = "Managers do not call managers"
type = "independence"
modules = [
  "quookly.managers.recipe",
  "quookly.managers.planning",
  "quookly.managers.pantry",
  "quookly.managers.cooking",
  "quookly.managers.engagement",
]

[[tool.importlinter.contracts]]
name = "Rule engines are pure"
type = "forbidden"
source_modules = [
  "quookly.engines.measure",
  "quookly.engines.suitability",
  "quookly.engines.nutrition",
  "quookly.engines.replenishment",
  "quookly.engines.scoring",
  "quookly.engines.execution",
  "quookly.engines.onboarding",
]
forbidden_modules = ["quookly.access"]
```

The third contract is the one that matters most: it is ADR-006 expressed as a build failure.

**Cost.** One more dev dependency and a contract file to maintain as the package layout evolves.

---

## ADR-009 SQLite by default, Postgres opt-in

**Status:** Proposed

**Context.** NFR-1 and NFR-3 target self-hosting on modest hardware.

**Decision.** SQLite is the default and requires no configuration. Postgres is supported through the
same resource access interfaces, selected by configuration.

**Rationale.** A household instance should not require a database server. The resource access layer
exists precisely so this choice does not reach business logic (V13).

**Cost.** Two backends to test. Full-text search differs between them, which `SearchIndexAccess`
must absorb — and this is where the abstraction will be under most strain.

---

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

**Cost.** The seed set must be maintained and translated per locale, and its licensing must be clean
— the same constraint that keeps [ADR-007](#adr-007-nutrition-source-is-pluggable-and-unresolved)
open applies to any recipe content that is not written for this project.

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
