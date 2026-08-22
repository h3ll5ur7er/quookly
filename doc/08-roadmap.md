# Roadmap

**Status: Planned.**

Ordered by architectural risk rather than by visible surface. Each phase ends with something that
works end to end and is covered by `just check`.

The sequencing principle: **build the thing the product is actually about first.** Structured
recipes and the de-bloat path are the differentiator. Social features and gamification are the parts
most likely to be built well by accident and least likely to matter if they are missing.

## Phase 0 — Foundations

**Goal:** the architecture is real and enforced before any domain code depends on it.

- ~~Package layout: `routes/`, `managers/`, `engines/`, `access/`, `utilities/`, `contracts/`~~ **Built**
- ~~`import-linter` contracts wired into `just backend check`~~ **Built**
  ([ADR-008](07-decisions.md#adr-008-enforce-the-call-rules-with-import-linter)) — per-service
  contracts follow their services
- ~~Persistence: SQLite only, SQLModel over async SQLAlchemy~~ **Built**
  ([ADR-009](07-decisions.md#adr-009-sqlite-only-to-begin-with),
  [ADR-018](07-decisions.md#adr-018-sqlmodel-as-the-orm))
- ~~Alembic migrations~~ **Built** — async env, SQLModel metadata, drift check in the test suite
- ~~First persisted entity: the cook account~~ **Built**
- ~~`Configuration` utility~~ **Built** ([ADR-019](07-decisions.md#adr-019-no-default-secret-key))
- ~~`Security` utility — Argon2 hashing, token issue and verification~~ **Built**
  ([ADR-020](07-decisions.md#adr-020-argon2-via-pwdlib-tokens-via-pyjwt))
- ~~`Diagnostics` utility — structured logging, request correlation~~ **Built**
  ([ADR-022](07-decisions.md#adr-022-standard-library-logging-configured-in-one-place))
- ~~Authentication: register, log in, JWT (UC-6.1)~~ **Built**
- ~~First-run admin bootstrap, closing permanently once a user exists (UC-10.1, FR-16)~~ **Built**
- ~~Angular shell: routing, auth guard, sign-in and bootstrap screens~~ **Built**
- ~~Design tokens, the four shipped themes, and the app shell~~ **Built**
  ([ADR-023](07-decisions.md#adr-023-theming-by-design-tokens-themes-as-data),
  [Design language](11-design-language.md))
- ~~i18n scaffolding — runtime locale, `$localize` catalogues, `en_GB`/`de_CH`/`fr_CH`~~ **Built**
  ([ADR-025](07-decisions.md#adr-025-runtime-locale-localize-catalogues-one-artefact))
- ~~Self-hosted display face, PWA manifest, service worker~~ **Built**
- **Mobile-first layout foundation and PWA shell** ([ADR-015](07-decisions.md#adr-015-mobile-first-installable-and-offline-where-it-matters))
- **TDD and the per-unit quality gate in force from the first commit** ([ADR-017](07-decisions.md#adr-017-test-driven-development-with-per-unit-quality-gates))

**Done when:** a fresh instance walks an operator through creating the first admin, that admin can
log in on a phone, and a layer violation fails the build. **Met.**

The mobile foundation belongs here rather than later. Retrofitting narrow-viewport layout onto
components authored for the desktop is a rewrite, not an adjustment — the same argument that puts
`MeasureEngine` in Phase 1.

## Phase 1 — The canonical recipe

**Goal:** structured recipes exist and can be read the way the product promises.

- ~~Domain model for recipe, ingredient line, step~~ **Built** — technique references arrive with
  the Academy (Phase 7). Step-to-line references landed in Phase 5 and turned out to want no model
  at all: they are read out of the instruction's own words
  ([ADR-040](07-decisions.md#adr-040-a-steps-ingredients-are-read-out-of-its-words-not-tagged))
- ~~Ingredient registry with locale-aware names~~ **Built**
  ([ADR-007](07-decisions.md#adr-007-nutrition-data-usda-fooddata-central-as-the-base))
- ~~`RecipeAccess`, `IngredientAccess`~~ **Built**; `EaterAccess` arrives with eaters (Phase 2)
- ~~`MeasureEngine`: conversion, density, yield scaling (V4)~~ **Built**
- ~~Unit preferences per ingredient kind (UC-6.2)~~ **Built**
- ~~Hand-authored recipes (UC-1.1); JSON import and export (UC-1.2, FR-11)~~ **Built**
- ~~Recipe list and detail pages with scaling and unit conversion (UC-2.1, UC-2.2)~~ **Built**
- ~~**Seed content**: ingredient registry and starter recipes, marked by origin (UC-10.4, FR-17,
  [ADR-016](07-decisions.md#adr-016-ship-seed-content-marked-and-upgradable))~~ **Built**

Nutrition — and with it the USDA FoodData Central seeding of
[ADR-007](07-decisions.md#adr-007-nutrition-data-usda-fooddata-central-as-the-base) — arrives in
Phase 6 with `NutritionEngine`. The Phase 1 registry carries names, kinds and densities: the working
approximations needed to turn a scraped cup into a weight, authored for this project rather than
taken from a dataset.

**Done when:** a recipe can be authored, viewed at any yield in the cook's preferred units, exported,
and re-imported without loss — and a fresh instance already has recipes to look at. **Met.**

Seed content lands here rather than in Phase 9 because it is what makes every later phase testable.
Planning, ranking, and cooking mode all need a recipe corpus, and hand-entering one before each test
run is a tax paid repeatedly.

`MeasureEngine` lands early on purpose: it is used by every later phase, and retrofitting unit
handling into working features is the change this architecture exists to avoid.

## Phase 2 — Eaters and suitability

**Goal:** the safety-critical path, before anything generates content.

- ~~Eater profiles, dietary constraints with severity, age bands (UC-6.3, UC-6.4)~~ **Built**
- ~~Appetite multipliers, summed to required yield (UC-6.5, FR-18)~~ **Built** — in `MeasureEngine`, because portion sizing is V4
- ~~`OnboardingEngine` and the new-cook setup flow (UC-10.2, UC-10.3, V16)~~ **Built** — including unit-preference and language endpoints, which setup needed and Phase 1 had only built as far as the access layer
- ~~Household screens: recording eaters, their constraints, and what the table adds up to~~ **Built**
- ~~Allergen classification in the ingredient registry~~ **Built**
- ~~`SuitabilityEngine` — pure, exhaustively tested (V5, [ADR-006](07-decisions.md#adr-006-allergen-determination-is-structural))~~ **Built**
- ~~Suitability verdicts with reasons surfaced in the UI, including *unknown*~~ **Built** — reasons on the recipe page, outcome alone on the list

**Done when:** a recipe can be evaluated against a named set of eaters and explains every verdict by
naming the ingredient responsible, and a new cook is walked from empty profile to ready household.
**Met.**

Onboarding lands here because this is the phase where there is finally something worth setting up.
Placed earlier it would collect preferences nothing yet consumes.

Deliberately **before** AI generation. Once generation exists there is pressure to trust its dietary
claims; having the structural judge already in place removes the temptation and the shortcut.

## Phase 3 — The de-bloat path

**Goal:** the founding use case.

- ~~`ModelAccess` with at least one local and one hosted provider (V3, FR-8)~~ **Built** — one OpenAI-shaped client ([ADR-026](07-decisions.md#adr-026-one-openai-shaped-wire-format-not-a-provider-plugin-system)), verified against a local vLLM
- ~~`WebContentAccess`: fetch and extract readable content~~ **Built** — prose plus embedded schema.org metadata ([ADR-028](07-decisions.md#adr-028-structured-metadata-is-fetched-not-preferred)), refusing the instance's own network ([ADR-027](07-decisions.md#adr-027-an-instance-will-not-fetch-its-own-network))
- ~~Recipe lines that carry no quantity — "salt, to taste"~~ **Built** — surfaced by Phase 3: the
  domain could not store a line real pages are full of, see [the domain model](06-domain-model.md#a-line-without-a-quantity)
- ~~`InterpretationEngine`: content to canonical recipe (V2)~~ **Built** — metadata first, a model over the prose otherwise; verified against live pages and a local Qwen3.6
- ~~URL import (UC-1.3), validation and failure reporting (FR-9)~~ **Built** — verified against live pages ([ADR-029](07-decisions.md#adr-029-an-ingredient-the-registry-does-not-know-is-recorded-and-reported), [ADR-030](07-decisions.md#adr-030-a-recipe-whose-yield-cannot-be-read-is-refused)); the screen for it follows
- ~~The screen for it: paste a link, see what came back and what needs a look~~ **Built**
- ~~Provider configuration in settings and via CLI (UC-8.2)~~ **Built** — configured by environment, reported by the app ([ADR-033](07-decisions.md#adr-033-the-inference-provider-is-configured-by-environment-and-reported-by-the-app))

**Done when:** pasting a recipe URL yields a structured recipe with resolved ingredients, or an
explicit, legible failure. **Met.**

This is the phase that determines whether the product is worth using.

## Phase 4 — Pantry and planning

**Goal:** the week actually gets planned.

- ~~`PantryAccess`, `PantryManager`: receive, adjust, expire, waste (UC-5.*)~~ **Built** — stock is
  held as lots rather than a total per ingredient
  ([ADR-034](07-decisions.md#adr-034-stock-is-held-as-lots-not-as-a-total-per-ingredient)), and
  adjusting is a different act from wasting
  ([ADR-035](07-decisions.md#adr-035-adjusting-stock-and-recording-waste-are-different-acts))
- ~~The pantry screen (UC-5.1–5.4)~~ **Built** — the shelf, what wants using, and one packet at a
  time; adjusting, wasting and removing are three different acts on that screen too
- ~~Reservation model ([ADR-004](07-decisions.md#adr-004-plans-reserve-stock-cooking-consumes-it)); releasing a reservation is a first-class path, as well tested as consuming one~~ **Built** — a
  claim exists only while it is held ([ADR-036](07-decisions.md#adr-036-a-reservation-exists-only-while-it-is-held)), and where the pantry and the plan disagree the fridge wins
- ~~`PlanAccess`: periods, slots, attendance (UC-4.1, UC-4.2)~~ **Built** — a slot exists before it
  has a recipe, because that is most of a week most of the time
- ~~`PlanningManager`, `PlanningEngine`: slots, attendance, suitability checks (UC-4.1–4.3)~~
  **Built** — a meal is sized to the appetites at it, flagged when it cannot be, and checked against
  the people coming; every change restates the plan's reservations
  ([ADR-038](07-decisions.md#adr-038-a-plans-reservations-are-restated-not-adjusted)). *Proposing*
  what to cook belongs with generation (Phase 6)
- ~~The plan screen (UC-4.1–4.4)~~ **Built** — a week laid out day by day with the gaps
  showing, one meal stated at a time, and the shopping list underneath it
- ~~A recipe's `serves` alongside its yield, so "makes 12 pancakes" can be scaled to a table~~
  **Built** — the deferred half of [ADR-030](07-decisions.md#adr-030-a-recipe-whose-yield-cannot-be-read-is-refused);
  read from a page's metadata and from its prose, and carried by
  [format 2](07-decisions.md#adr-012-export-format-is-the-import-format) of the interchange document
- ~~`ReplenishmentEngine`: shopping list net of stock (UC-4.4, V8)~~ **Built** — the packet going off
  first is the one drawn from, and the shopping list is what could not be drawn
- ~~Cook a meal, consume reservations (UC-4.5)~~ **Built** — one way, and idempotent: the food is
  eaten, and un-marking would mean re-adding stock that never came back
- ~~`EventBus` and the first events~~ **Built** — in-process and awaited
  ([ADR-039](07-decisions.md#adr-039-events-are-published-in-this-process-and-awaited)); `MealCooked`
  is the first, and the pantry is the first listener

**Done when:** a week can be planned for a household including a guest with a restriction, producing
a correct shopping list, and cooking a meal updates the pantry. **Met.**

## Phase 5 — Cooking mode

**Goal:** the app is useful while standing at the hob, not just while planning at a desk.

- ~~`ExecutionEngine`: mise-en-place grouping, the lines each step names, long-lead work brought
  forward (V15, [ADR-040](07-decisions.md#adr-040-a-steps-ingredients-are-read-out-of-its-words-not-tagged),
  [ADR-041](07-decisions.md#adr-041-work-done-the-day-before-is-lifted-out-only-from-the-front))~~
  **Built.** Timer specs are the steps' own durations, so there was nothing left to specify
- ~~Per-step attention, and a recipe's hands-on and total time derived from it (UC-2.6, FR-23,
  [ADR-037](07-decisions.md#adr-037-how-long-a-recipe-takes-is-two-numbers-both-derived))~~
  **Built.** Overlap turned out not to want inferring: a recipe never says which steps run together,
  and a guess makes the total *shorter* than the truth — the one direction that makes somebody late
- ~~`CookingSessionAccess` and `CookingManager`: sessions, progress, resumption (UC-9.1–9.3, 9.7)~~
  **Built.** A session executes a *planned meal*
  ([ADR-042](07-decisions.md#adr-042-a-cooking-session-executes-a-planned-meal)), so there is one
  record of a meal and one way its stock is spent
- ~~Timers held as instants server-side, ticked on the client (UC-9.4,
  [ADR-013](07-decisions.md#adr-013-cooking-sessions-are-server-side-state-timers-store-instants))~~
  **Built**, one per step — a kitchen has the oven on while something else simmers
- ~~Completion and abandonment, driving stock through the bus (UC-9.6, UC-9.8, FR-19)~~ **Built.**
  Abandoning publishes nothing: the meal is still planned, and releasing what it held would take it
  off the shopping list at the same time
- ~~Cooking-mode UI: one step per screen, wake lock, thumb-reachable controls (NFR-12)~~ **Built.**
  The application's own navigation goes away with it: a section bar under a half-finished recipe is
  an invitation to leave in the middle of one
- ~~Offline tolerance for the active session (NFR-13)~~ **Built.** The meal is kept as the server
  last described it, turning the page works whether or not the request lands, and the position is
  sent again when the network returns. Timers are the exception and say so: their whole design is
  that the server stamps the instant, and one stamped on the way back would lose however long the
  connection was down

**Done when:** a cook can start a session on a tablet, prep from the mise-en-place list, run a timer,
lock the screen, pick the session up on their phone, finish, and see the pantry updated. **Met.**

Required Phase 4 for reservations. Phase 7's Academy still owes in-step technique lookup (UC-9.5),
which lands after the Academy without blocking anything here.

## Phase 6 — Generation and discovery

**Goal:** the app proposes rather than waits.

- ~~`GenerationEngine`: from ingredients, name, description (UC-1.4, UC-1.5)~~ **Built**. A recipe
  the household cannot eat is refused with its verdict rather than stored and marked
  ([ADR-047](07-decisions.md#adr-047-a-generated-recipe-is-refused-not-warned-about)) — it was asked
  for on these people's behalf. From a **photograph** (UC-1.6) waits for a vision model: ADR-026's
  wire format carries text, and images are an addition to `ModelAccess` rather than to this engine
- ~~Variant derivation (UC-1.7)~~ **Built** for dietary adaptation and substitution. Scaling is left
  out on purpose: a recipe already scales to any yield through `MeasureEngine`, and asking a model to
  multiply is asking it to do arithmetic
- ~~`SearchIndexAccess` and full-text search (UC-3.1)~~ **Built** over SQLite FTS5: titles, the
  ingredients in every language the registry knows them by, and summaries. UC-3.2's filters by tag,
  cuisine and difficulty wait for a recipe to have those fields; time and dietary suitability are
  already on the row
- ~~`RankingEngine`: pantry coverage and expiry urgency (UC-3.3, UC-3.4)~~ **Built**
  ([ADR-046](07-decisions.md#adr-046-a-suggestion-earns-its-place-by-saving-something)). What is about
  to go off outweighs a full cupboard, and every suggestion says why it is where it is
- ~~`NutritionEngine` and nutrition display (UC-2.3)~~ **Built**, over the **Swiss Food Composition
  Database** with a configured cascade behind it
  ([ADR-045](07-decisions.md#adr-045-composition-data-is-tried-in-a-configured-order-nearest-table-first)).
  USDA is the last resort rather than the base: composition data measures a food supply, and US flour
  is fortified where Swiss flour is not. Ciqual, CoFID and USDA are places in the order waiting for
  their data

**Done when:** "what should I cook this week" returns ranked, suitable suggestions that use up what
is about to expire.

## Phase 6b — One product, not five screens

**Goal:** the parts stop reading as separate ideas taped together.

Each phase built a screen and each screen was defensible on its own. Together they were not a
product: a laptop got a phone layout, settings existed only for whoever had read the routing table,
there was no way in for somebody who did not already have an account, and no screen led to the next.

- ~~Real breakpoints, chrome that becomes a sidebar, collections that become grids~~ **Built** —
  see [ADR-015](07-decisions.md#adr-015-mobile-first-installable-and-offline-where-it-matters)
- ~~A reachable Settings page~~ **Built** — household, units, theme, language and the account moved
  under it, and out of the navigation bar
- ~~A home screen that answers "what now"~~ **Built** — a greeting, what is about to spoil, tonight's
  meal, what is left to buy
- ~~A shopping list of its own~~ **Built** — its own destination, because a cook holding a basket
  should not navigate a plan to reach it
- ~~Signing out~~ **Built**, under Settings
- ~~Ticking items off the shopping list~~ **Built** — server-side, because shopping is the one
  thing two people do at once, and a tick remembers the quantity it was made at
  ([ADR-048](07-decisions.md#adr-048-a-ticked-shopping-line-remembers-what-it-was-ticked-at))
- ~~Cross-links: **start cooking now** and **add to plan** on a recipe, **show recipe** on a
  plan~~ **Built** — and it turned out to be no change to V15 at all. ADR-042 had already written
  the answer: cooking a recipe outright is *plan it for today, then cook it*, composed in the route
- A landing page for somebody who arrives without an account
- ~~**Signing up by application** — anybody may apply, an admin approves~~ **Built**
  ([ADR-049](07-decisions.md#adr-049-an-account-is-applied-for-and-an-administrator-answers)) —
  the apply form, three different sign-in refusals, and the admin queue under Settings
- ~~A landing page for somebody who arrives without an account~~ **Built** — `/` is the landing
  page to a visitor and the home dashboard to a cook, matched by `canMatch` rather than redirected,
  so the front door is not at a URL nobody would type

Placed after Phase 6 because there was nothing to tie together before there was something on each
screen, and before Phase 7 because an Academy inside a product that reads as a prototype is
studying for an exam nobody has sat.

**This phase is the cut line for a first release.** Everything above is built, so the working branch
merges to `main`; Phases 7 and 8 are add-ons that ship afterwards.

## Phase 7 — Academy and the registry

**Goal:** the learning surface, and the reference data behind it.

The two belong together. An Academy is where a cook goes to look something up, and the largest
body of things to look up in Quookly is the ingredient registry — which is also the one part of the
system a cook currently cannot see or correct without editing code.

### The Academy

- `AcademyAccess`, techniques, definitions, tips
- Technique references from recipe steps (UC-2.5)
- In-step technique lookup while cooking (UC-9.5)
- Contribution and moderation (UC-7.4)
- Public Academy page

### The ingredient registry, visible and correctable

**Today:** importing a recipe already creates registry entries for ingredients nobody has recorded
(`RecipeManager`, `Origin.USER`). It has to — a line that resolves to nothing cannot be shopped for,
scaled or judged. But what it creates is a guess: `kind` is assumed `SOLID`, `density` is absent, and
allergens are deliberately left **unclassified** rather than empty, because nobody has looked
([ADR-006](07-decisions.md#adr-006-allergen-determination-is-structural)).

Nothing surfaces those guesses and nothing can correct them. A cook who imports a French recipe gets
`crème fraîche` filed as a solid with no density, and the only way to fix it is a migration.

What this phase owes:

- **A registry screen** — every ingredient, its kind, density, per-locale names, allergen
  classification, and where it came from. Searchable, because it is the largest list in the app.
- **Editing an ingredient**, and merging two that are the same thing under different names. Merging
  is the operation that matters: an import that created `plain flour` beside a registry that already
  had `wheat flour` has split one ingredient in two, and every allergen and nutrition fact now
  answers for half a kitchen.
- **A "needs approval" state.** Distinct from *unclassified allergens*, which is a fact about
  knowledge; this is a fact about **review**. An entry an import invented is usable immediately —
  refusing to import until an admin wakes up would be absurd — but it is flagged, and an admin can
  approve it, correct it, or merge it away.
- **Best-effort nutrition matching on creation.** Ask the configured source tree (Swiss, then
  European, then the rest, then American — [ADR-045](07-decisions.md#adr-045-composition-data-is-tried-in-a-configured-order-nearest-table-first)) for a row matching the
  new name, and attach it as a *proposal* rather than as a figure. A matched profile a human has not
  confirmed is not the same fact as a seeded one, and the same rule applies as everywhere: an
  unconfirmed match must not read as a confirmed one.
- **The registry as an Academy page** — what an ingredient is, what it is called elsewhere, what it
  weighs, what it contains, what it can be swapped for. That is reference material, which is what an
  Academy is for.

Placed here rather than in Phase 6b because none of it blocks a first release: the guesses are
already conservative in the direction that matters — an unclassified allergen never claims a recipe
is safe.

## Phase 8 — Community and engagement

**Goal:** recipes circulate.

- Publishing, following, ratings, comments (UC-7.1–7.3)
- `ScoringEngine`, `EngagementManager` driven by events (V11)
- Badges, points, leaderboards by period, category, and group (UC-7.5)

Last on purpose. It is the most volatile area, the least consequential when it changes, and the one
whose absence costs the product least.

## Phase 8b — Reading a recipe in your own language

**Goal:** a recipe written in one language is read in another, without losing the original.

**Status: proposed**, see [ADR-032](07-decisions.md#adr-032-proposed-recipes-are-stored-in-their-own-language-and-read-in-yours)
and [V17](03-volatility-analysis.md#v17-content-translation).

Most of it already exists. Quantities, durations and temperatures are language-neutral by
construction, and ingredient names resolve per locale through the registry. What is missing:

- ~~Serve recipes in the **cook's** language rather than a hardcoded `en-GB`~~ **Built** — the
  plumbing had been there since Phase 1; the routes simply never asked for anything but English
- Record the language a recipe is written in
- `TranslationEngine` — a capability engine over `ModelAccess`, the same shape as
  `InterpretationEngine`
- Translations stored beside the original, derived lazily on first request for a language
- Per-locale names for ingredients an import created, so a foreign import is as readable as a
  seeded one

Placed here rather than earlier because it is worth having only once there is a corpus worth
reading, and because it depends on nothing in Phase 9.

## Phase 9 — Self-hosting polish

**Goal:** someone other than us runs it.

- Container image serving API and frontend from one artefact (NFR-2)
- Compose files: standalone, with Postgres, with Ollama
- Backup, restore, and upgrade paths (UC-8.1)
- Bulk import and export via CLI (UC-8.3)
- Installation documentation validated on a clean machine
- `de_CH` and `fr_CH` translations complete (FR-10)

## Cross-cutting, every phase

- Test-first: the specification becomes a failing test before it becomes code
  ([ADR-017](07-decisions.md#adr-017-test-driven-development-with-per-unit-quality-gates))
- The per-unit quality gate runs at the end of every unit, not every pull request
- Mobile viewport checked as UI is built, not retrofitted (NFR-11)
- Strict mypy and strict Angular templates stay green
- New services get tests at their own layer; rule engines get exhaustive unit tests
- `just openapi` after every API change
- Accessibility checked as UI is built, not retrofitted (NFR-7)
- Each phase updates these documents when it changes a decision

## Known risks

| Risk | Mitigation |
| --- | --- |
| Interpretation quality (V2) is the product, and is hard | Phase 3 is deliberately early; build a fixture corpus of real messy pages and measure against it. Checked against live pages, the major publishers embed complete schema.org recipes, which moves much of the risk from *reading prose well* to *knowing when to trust the metadata* |
| Overlay datasets carry mandatory attribution, which is easy to omit | FR-20 stores source and licence per nutrient profile, so attribution is generated from the data actually used rather than remembered by hand |
| Ingredient registry needs curation a self-hoster cannot provide | Ship a base registry, allow local additions; decide ownership in [open questions](06-domain-model.md#open-questions) |
| Local models may be too weak for reliable structured extraction | Support hosted providers from Phase 3; treat structured-output failure as a normal, reported outcome |
| Scope: the feature list is very large | Phases 0–4 are the product; 5–8 are extension |
