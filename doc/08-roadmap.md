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
- `Diagnostics` and `Security` utilities
- Authentication: register, log in, JWT (UC-6.1)
- First-run admin bootstrap, closing permanently once a user exists (UC-10.1, FR-16)
- Angular shell: routing, auth guard, layout, i18n scaffolding
- **Mobile-first layout foundation and PWA shell** ([ADR-015](07-decisions.md#adr-015-mobile-first-installable-and-offline-where-it-matters))
- **TDD and the per-unit quality gate in force from the first commit** ([ADR-017](07-decisions.md#adr-017-test-driven-development-with-per-unit-quality-gates))

**Done when:** a fresh instance walks an operator through creating the first admin, that admin can
log in on a phone, and a layer violation fails the build.

The mobile foundation belongs here rather than later. Retrofitting narrow-viewport layout onto
components authored for the desktop is a rewrite, not an adjustment — the same argument that puts
`MeasureEngine` in Phase 1.

## Phase 1 — The canonical recipe

**Goal:** structured recipes exist and can be read the way the product promises.

- Domain model for recipe, ingredient line, step, technique reference
- Ingredient registry with locale-aware names, seeded from USDA FoodData Central, with the Swiss
  and UK overlays for the target locales
  ([ADR-007](07-decisions.md#adr-007-nutrition-data-usda-fooddata-central-as-the-base))
- `RecipeAccess`, `IngredientAccess`, `EaterAccess`
- `MeasureEngine`: conversion, density, yield scaling (V4)
- Unit preferences per ingredient kind (UC-6.2)
- Hand-authored recipes (UC-1.1); JSON import and export (UC-1.2, FR-11)
- Recipe list and detail pages with scaling and unit conversion (UC-2.1, UC-2.2)
- **Seed content**: ingredient registry and starter recipes, marked by origin (UC-10.4, FR-17,
  [ADR-016](07-decisions.md#adr-016-ship-seed-content-marked-and-upgradable))

**Done when:** a recipe can be authored, viewed at any yield in the cook's preferred units, exported,
and re-imported without loss — and a fresh instance already has recipes to look at.

Seed content lands here rather than in Phase 9 because it is what makes every later phase testable.
Planning, ranking, and cooking mode all need a recipe corpus, and hand-entering one before each test
run is a tax paid repeatedly.

`MeasureEngine` lands early on purpose: it is used by every later phase, and retrofitting unit
handling into working features is the change this architecture exists to avoid.

## Phase 2 — Eaters and suitability

**Goal:** the safety-critical path, before anything generates content.

- Eater profiles, dietary constraints with severity, age bands (UC-6.3, UC-6.4)
- Appetite multipliers, summed to required yield (UC-6.5, FR-18)
- `OnboardingEngine` and the new-cook setup flow (UC-10.2, UC-10.3, V16)
- Allergen classification in the ingredient registry
- `SuitabilityEngine` — pure, exhaustively tested (V5, [ADR-006](07-decisions.md#adr-006-allergen-determination-is-structural))
- Suitability verdicts with reasons surfaced in the UI, including *unknown*

**Done when:** a recipe can be evaluated against a named set of eaters and explains every verdict by
naming the ingredient responsible, and a new cook is walked from empty profile to ready household.

Onboarding lands here because this is the phase where there is finally something worth setting up.
Placed earlier it would collect preferences nothing yet consumes.

Deliberately **before** AI generation. Once generation exists there is pressure to trust its dietary
claims; having the structural judge already in place removes the temptation and the shortcut.

## Phase 3 — The de-bloat path

**Goal:** the founding use case.

- `ModelAccess` with at least one local and one hosted provider (V3, FR-8)
- `WebContentAccess`: fetch and extract readable content
- `InterpretationEngine`: content to canonical recipe (V2)
- URL import (UC-1.3), validation and failure reporting (FR-9)
- Provider configuration in settings and via CLI (UC-8.2)

**Done when:** pasting a recipe URL yields a structured recipe with resolved ingredients, or an
explicit, legible failure.

This is the phase that determines whether the product is worth using.

## Phase 4 — Pantry and planning

**Goal:** the week actually gets planned.

- `PantryAccess`, `PantryManager`: receive, adjust, expire, waste (UC-5.*)
- Reservation model ([ADR-004](07-decisions.md#adr-004-plans-reserve-stock-cooking-consumes-it)); releasing a reservation is a first-class path, as well tested as consuming one
- `PlanAccess`, `PlanningManager`, `PlanningEngine`: slots, attendance, suitability checks (UC-4.1–4.3)
- `ReplenishmentEngine`: shopping list net of stock (UC-4.4, V8)
- Cook a meal, consume reservations (UC-4.5)
- `EventBus` and the first events

**Done when:** a week can be planned for a household including a guest with a restriction, producing
a correct shopping list, and cooking a meal updates the pantry.

## Phase 5 — Cooking mode

**Goal:** the app is useful while standing at the hob, not just while planning at a desk.

- `ExecutionEngine`: mise-en-place grouping, step ordering, parallelism, timer specs (V15)
- `CookingSessionAccess` and `CookingManager`: sessions, progress, resumption (UC-9.1–9.3, 9.7)
- Timers held as instants server-side, ticked on the client (UC-9.4,
  [ADR-013](07-decisions.md#adr-013-cooking-sessions-are-server-side-state-timers-store-instants))
- Completion and abandonment, driving stock through the bus (UC-9.6, UC-9.8, FR-19)
- Cooking-mode UI: one step per screen, wake lock, thumb-reachable controls (NFR-12)
- Offline tolerance for the active session (NFR-13)

**Done when:** a cook can start a session on a tablet, prep from the mise-en-place list, run a timer,
lock the screen, pick the session up on their phone, finish, and see the pantry updated.

Requires Phase 4 for reservations, and Phase 7's Academy for in-step technique lookup (UC-9.5) —
that last piece can land after the Academy without blocking the rest.

## Phase 6 — Generation and discovery

**Goal:** the app proposes rather than waits.

- `GenerationEngine`: from ingredients, name, description, tags, photograph (UC-1.4–1.6)
- Variant derivation (UC-1.7)
- `SearchIndexAccess` and full-text search (UC-3.1, UC-3.2)
- `RankingEngine`: pantry coverage and expiry urgency (UC-3.3, UC-3.4)
- `NutritionEngine` and nutrition display (UC-2.3), over the USDA FoodData Central base set

**Done when:** "what should I cook this week" returns ranked, suitable suggestions that use up what
is about to expire.

## Phase 7 — Academy

**Goal:** the learning surface.

- `AcademyAccess`, techniques, definitions, tips
- Technique references from recipe steps (UC-2.5)
- Contribution and moderation (UC-7.4)
- Public Academy page

## Phase 8 — Community and engagement

**Goal:** recipes circulate.

- Publishing, following, ratings, comments (UC-7.1–7.3)
- `ScoringEngine`, `EngagementManager` driven by events (V11)
- Badges, points, leaderboards by period, category, and group (UC-7.5)

Last on purpose. It is the most volatile area, the least consequential when it changes, and the one
whose absence costs the product least.

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
| Interpretation quality (V2) is the product, and is hard | Phase 3 is deliberately early; build a fixture corpus of real messy pages and measure against it |
| Overlay datasets carry mandatory attribution, which is easy to omit | FR-20 stores source and licence per nutrient profile, so attribution is generated from the data actually used rather than remembered by hand |
| Ingredient registry needs curation a self-hoster cannot provide | Ship a base registry, allow local additions; decide ownership in [open questions](06-domain-model.md#open-questions) |
| Local models may be too weak for reliable structured extraction | Support hosted providers from Phase 3; treat structured-output failure as a normal, reported outcome |
| Scope: the feature list is very large | Phases 0–4 are the product; 5–8 are extension |
