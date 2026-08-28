# Roadmap

**Status: Phases 0 through 6b are complete and released. Phase 7 is next; Phases 8, 8b and 9
follow.**

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
is about to expire. **Met.**

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
- ~~**Signing up by application** — anybody may apply, an admin approves~~ **Built**
  ([ADR-049](07-decisions.md#adr-049-an-account-is-applied-for-and-an-administrator-answers)) —
  the apply form, three different sign-in refusals, and the admin queue under Settings
- ~~A landing page for somebody who arrives without an account~~ **Built** — `/` is the landing
  page to a visitor and the home dashboard to a cook, matched by `canMatch` rather than redirected,
  so the front door is not at a URL nobody would type

Placed after Phase 6 because there was nothing to tie together before there was something on each
screen, and before Phase 7 because an Academy inside a product that reads as a prototype is
studying for an exam nobody has sat.

**This phase was the cut line for a first release.** Everything above is built and merged to
`master`; Phases 7 and 8 are add-ons that ship afterwards. **Met.**

## Phase 7 — Academy and the registry

**Goal:** the learning surface, and the reference data behind it.

The two belong together. An Academy is where a cook goes to look something up, and the largest
body of things to look up in Quookly is the ingredient registry — which is also the one part of the
system a cook currently cannot see or correct without editing code.

### The Academy

**Designed** — [ADR-054](07-decisions.md#adr-054-academymanager-is-reinstated),
[ADR-055](07-decisions.md#adr-055-a-step-finds-its-techniques-by-the-words-it-already-uses),
[ADR-056](07-decisions.md#adr-056-a-generated-explanation-is-marked-unreviewed-and-never-an-input-to-a-judgement),
[ADR-057](07-decisions.md#adr-057-the-academy-is-sections-of-pages-not-a-table-of-techniques),
[ADR-058](07-decisions.md#adr-058-ambiguity-is-shown-where-a-person-resolves-it-and-refused-where-something-computes-on-it),
[ADR-059](07-decisions.md#adr-059-a-step-may-name-its-own-links-and-a-recipe-may-be-edited),
[V18](03-volatility-analysis.md#v18-explanation), [the page](06-domain-model.md#an-academy-page) and
[the flows](05-use-case-flows.md#uc-25-and-uc-95-look-up-a-term-from-a-recipe-or-from-the-step-being-cooked).
Not built.

There is no published table to derive this from, the way the ingredient registry was derived from the
Swiss database. The corpus comes from three places instead — a hand-written seed, what cooks write,
and what a model composes on request — and the order below is chosen so that the part which can be
*wrong* arrives last, on top of something that already works without it.

The unit is a **page with a kind**, not a technique: sections for techniques, for ingredients, and for
whatever follows. ~~Fifty seeded technique pages~~ **written** — `seed/techniques.json`, in three
languages, with the spellings a step is actually written with.

0. ~~**A recipe can be edited.**~~ **Built** on the backend — `PUT /recipes/{id}` replaces a recipe
   with how it should now read, and `archived`/`restored` put one away and bring it back. Not an
   Academy feature at all, and listed here because the Academy found it: a recipe could be created
   and never changed, so a typo in an imported recipe was permanent. Everyone edits their own and
   another cook's is *absent rather than forbidden*; archived rather than deleted, because plans,
   cooked meals and shopping ticks point at a recipe.

   The screens came with it, and one of them was missing before any of this: there was **no manual
   authoring form at all**. UC-1.1 was built on the backend and the only ways in were an import or a
   model. `/recipes/new` and `/recipes/:id/edit` are one form — writing and correcting differ only
   in whether it arrives filled in — and the detail page carries *Correct this recipe* and *Put it
   away*, the second behind a confirmation because it takes a recipe out of the list and out of
   search.
1. ~~**`AcademyAccess`, and the seeded pages loaded.**~~ **Built** on the backend — `GET /academy`
   lists a section, `GET /academy/{slug}` reads a page in the cook's language, and
   `GET /academy/terms/{term}` answers with everyone who claims a term. Fifty pages install at
   start-up, and a second boot adds no second copy. The kind is stamped from the seed file's
   `section` rather than repeated on every page. *An Academy nobody can add to is still an Academy* —
   there is no writing, no matching and no model here. The screens follow.
2. ~~**Spotting terms in a step**~~ **Built** — `MatchingEngine.mentioned`, pure, a table of steps
   and expected offsets. Compared token by token against the *original* text, because folding can
   change a string's length and an offset into the folded form underlines the wrong words. Longest
   first, no overlaps, and no term reaching across a full stop. Nothing rendered yet.

   Measuring it against the shipped corpus added a field: a canonical name that is also an ordinary
   word keeps being the name and stops being something a step is matched against. German `sieben` is
   *to sift* and *the number seven*.
3. ~~**Terms marked on the recipe page (UC-2.5)**, then **in cooking mode (UC-9.5)**~~ **Built** —
   and with them the first Academy screens, because a link needs somewhere to lead. A step's words
   are cut into the parts that link and the parts that do not, so what is shown is the cook's own
   text. A term with several claimants offers a chooser at `/academy/terms/{term}`; a page whose
   name is shared carries a hatnote naming the others.
4. **An administrator edits a page.** ~~Text and translations~~ **Built** — one language's
   wording at a time, replaced whole rather than patched, and a language the page does not speak
   yet is how a translation arrives. Approving is separate: fixing a sentence is not saying
   somebody has read the page
   ([ADR-051](07-decisions.md#adr-051-whether-an-entry-has-been-reviewed-is-a-different-column-from-whether-it-has-been-classified)),
   and correcting one does not claim a person wrote it
   ([ADR-056](07-decisions.md#adr-056-a-generated-explanation-is-marked-unreviewed-and-never-an-input-to-a-judgement)).
   ~~**Pictures**~~ **Built** too, and they brought `MediaAccess` forward out of Phase 8. Files sit
   in a directory beside the database, an upload is re-encoded rather than kept as it arrived, and a
   file is named by a UUID the database refers to. Nothing deletes on its own: taking a picture off a
   page leaves the file, and collecting what is no longer referred to is owed to the CLI.
5. ~~**Explicit links in a step**, `[[slug|the words as written]]`~~ **Built** — for what automatic
   reading cannot know, which is mainly *which* flour "the flour" means. An author's link wins over
   automatic spotting for the words it covers; the rest of the step is still read as before.

   Two texts fall out of it, and the split is the whole trick: a reader gets the instruction with
   the markup resolved and the marks positioned into *that*, and an edit form is filled from what is
   stored. The obvious shortcut — one text, filled from what is shown — deletes an author's link the
   first time somebody fixes a typo in the same sentence. Model-composed instructions have the
   syntax stripped at the single point where a read recipe becomes a stored one: generating, varying
   and importing all pass through it, and writing a link is deciding what a word means
   ([ADR-053](07-decisions.md#adr-053-the-matcher-ranks-a-person-decides)).
6. ~~**Cook-authored pages, and approving them (UC-7.4, moderation half).**~~ **Built** —
   any signed-in cook writes a page, in their own language; a page written in one is one
   the other two fall back from, so contributing does not require being a translator.

   ADR-051's approval axis, and it gained a consequence. *Marking* an unreviewed page is
   what [ADR-056](07-decisions.md#adr-056-a-generated-explanation-is-marked-unreviewed-and-never-an-input-to-a-judgement)
   does for generated prose, and it is not enough here: a page **claims terms**, and a term
   is matched into every step on the instance that uses the word. A mark works when the
   reader has come to the page; it does nothing when the page arrives underlined inside a
   recipe they wrote. So approval gates *term-claiming* rather than readability
   ([ADR-060](07-decisions.md#adr-060-an-unreviewed-page-can-be-read-but-cannot-attach-itself-to-somebody-elses-recipe)):
   until somebody has read it, it is a page in the Academy and not a word in anybody's
   recipe. The author may keep working on it until then, because somebody who cannot fix
   their own typo will not write a second page.

   Declining archives, like a recipe put away. Recognition for contributing is V11 and
   waits for Phase 8.
7. ~~**An ingredient section**, sitting over the registry rather than duplicating it~~ **Built** —
   a page of kind `ingredient` **names** a registry entry and shows that entry's facts by reading
   them. It stores none of them.

   The reason is not tidiness. Written twice, the facts disagree — and not symmetrically: a cook
   reads the page, because the page is the thing written for a reader, while `SuitabilityEngine`
   reads the registry. A paragraph saying *"contains no gluten"* would be believed by the person and
   ignored by the machine, which is the direction
   [ADR-006](07-decisions.md#adr-006-suitability-and-allergen-conclusions-are-computed-from-structured-ingredients)
   exists to prevent. So the page reads them, and inherits the registry's own distinction:
   **unclassified is shown as unclassified**, never as an empty list
   ([ADR-061](07-decisions.md#adr-061-an-ingredient-page-names-its-entry-and-never-restates-what-the-registry-computes-on)).

   Several pages may name one food, and nothing computes on which — the Academy's existing stance
   on ambiguity, and what saves a tiebreak when two entries are merged. Merging is where
   [ADR-052](07-decisions.md#adr-052-merging-repoints-an-eaters-constraints-which-nothing-in-the-database-protects)'s
   eight relationships became **nine**.

   Two things fell out of building it. Browsing reported every page as a technique, because the kind
   came from the *query* rather than from the page — invisible while the Academy had one section.
   And the way back from the facts to the prose is asked of the Academy rather than answered by the
   registry entry: the registry's contracts already sit underneath the Academy's, so answering it
   there would have made the two import each other.
8. ~~**Generating a page nobody has written.**~~ **Built** — last on purpose, and it stayed small
   because everything it needed was already decided.

   **Techniques only.** A page about a food sits directly beside a panel of the registry's computed
   facts, and generated prose next to computed facts is the one arrangement where a reader cannot
   tell which half was checked — a paragraph saying *"a good gluten-free option"* under a panel
   saying **gluten**. Marking the page does not fix that, because the mark is on the page while the
   contradiction is between two paragraphs of it
   ([ADR-062](07-decisions.md#adr-062-a-model-may-explain-a-technique-and-may-not-write-about-a-food)).

   The rest composed from what was already there: the page is marked as a model's and as read by
   nobody, and *because* it is unreviewed it claims no terms
   ([ADR-060](07-decisions.md#adr-060-an-unreviewed-page-can-be-read-but-cannot-attach-itself-to-somebody-elses-recipe)).
   The cook who asked gets their page; the instance does not get a new word in everybody's recipes
   until a person has read it. Nobody here is recorded as having written it — asking for a page is
   not writing one.

   Building it turned up a gap that had nothing to do with models: **the screen that says "nobody
   has explained that yet" could not be reached at all.** A word nobody has explained is a word no
   recipe underlines, so the term screen had no way in. The Academy has a lookup now, which it
   wanted anyway.

   Optional by construction, and proved so: the e2e harness runs with no provider, and the spec for
   this feature is the honest failure — *nobody has explained that yet, and this instance has no
   model to ask*.
9. ~~**A public Academy page.** Readable without an account; generation is not.~~ **Built** —
   listing, reading a page and asking which pages claim a term need no account. Writing,
   correcting, approving, declining, illustrating and **asking a model** still do; the last of
   those would otherwise be an open relay to a paid provider.

   The load-bearing half is *which* pages: **only what somebody here has read**. An unreviewed
   page stays readable by the people here — that is
   [ADR-060](07-decisions.md#adr-060-an-unreviewed-page-can-be-read-but-cannot-attach-itself-to-somebody-elses-recipe),
   and the author has to see their draft — but publishing it is a different act. Without the rule,
   anyone let through the door could publish arbitrary text to the open internet under the
   instance's name, and a generated page nobody had read would be published by the act of asking
   for it
   ([ADR-063](07-decisions.md#adr-063-the-academy-is-readable-without-an-account-and-only-what-somebody-here-has-read-is)).

   **A picture is public exactly when its page is** — a query, not an unguessable id. Today every
   picture here is an Academy picture, so the first recipe photograph would otherwise have been
   published by a decision nobody revisited.

   A signed-out reader says which language they want, having no cook record to take one from; a
   stranger asking for the review queue is told there are none rather than quietly handed the
   published list. And the landing page links to it, because a public Academy nobody can find from
   the front door is reachable only by typing a URL.

**Phase 7 is complete.** The remaining Academy work is the CLI's, and deliberately later: see
Phase 9.

The registry half of this phase is where the shape came from. A page has a slug, canonical names and
spellings per locale, a provenance and a review state, and the same things go wrong with it — which
means the correcting, renaming and approving already built have obvious analogues.

### The ingredient registry, visible and correctable

**Since [ADR-050](07-decisions.md#adr-050-the-shipped-registry-is-derived-from-a-published-table-and-says-when-it-does-not-know)**
the registry ships with roughly nine hundred generic foods derived from the Swiss database, named in
English, German and French, with nutrition and — where the source can answer completely — allergens.
That closes most of the gap a fresh instance had. It does not close the rest:

**Today:** importing a recipe still creates registry entries for ingredients nobody has recorded
(`RecipeManager`, `Origin.USER`). It has to — a line that resolves to nothing cannot be shopped for,
scaled or judged. But what it creates is a guess: `kind` is assumed `SOLID`, `density` is absent, and
allergens are deliberately left **unclassified** rather than empty, because nobody has looked
([ADR-006](07-decisions.md#adr-006-allergen-determination-is-structural)).

Nothing surfaces those guesses and nothing can correct them. A cook who imports a French recipe gets
`crème fraîche` filed as a solid with no density, and the only way to fix it is a migration.

What this phase owes:

- ~~**A registry screen** — every ingredient, its kind, density, per-locale names, allergen
  classification, and where it came from. Searchable, because it is the largest list in the app.~~
  **Built** — under Settings, paged and counted. It shows the three fields an import guesses at
  (kind, density, origin) and narrows to the entries imports invented, which is the pile worth
  reviewing. *Unclassified* allergens read as "not checked" rather than as an empty list, because
  the empty list is where unknown becomes safe ([ADR-006](07-decisions.md#adr-006-allergen-determination-is-structural)).
  Per-locale names are not on the row: nine hundred entries times three languages is not a list,
  and they belong on the entry itself — which arrives with editing.
- ~~**Editing an ingredient**~~ **Built** — an entry screen with the three guessed facts (kind,
  density, piece weight), the fourteen allergen classes, and what it is called per locale. Three
  separate acts on three separate endpoints, which is the point: *correcting* a density, *recording*
  what is inside, and *approving* the entry are different statements, and a single PUT of the whole
  entry would let a correction that omitted allergens silently unclassify a known-milk ingredient
  ([ADR-006](07-decisions.md#adr-006-allergen-determination-is-structural)). Renaming is a fourth
  act again: adding a spelling and deciding which spelling *is* the name are different, and the old
  name is demoted rather than deleted — pages out there still use it, and an import that stopped
  resolving it would invent the duplicate this screen exists to clean up.
- ~~**Merging two entries that are the same thing under different names.**~~ **Built**
  ([ADR-052](07-decisions.md#adr-052-merging-repoints-an-eaters-constraints-which-nothing-in-the-database-protects)).
  Eight relationships move, and the eighth — an eater's dietary constraints — is joined by text
  rather than by a foreign key, so it is the one that fails silently and in the dangerous direction.
  Allergens merge as a union so a merge can never make a food look safer; the loser's names survive
  as spellings, or the next import invents the duplicate again.
- ~~**A "needs approval" state.** Distinct from *unclassified allergens*, which is a fact about
  knowledge; this is a fact about **review**. An entry an import invented is usable immediately —
  refusing to import until an admin wakes up would be absurd — but it is flagged, and an admin can
  approve it, correct it, or merge it away.~~ **Built**
  ([ADR-051](07-decisions.md#adr-051-whether-an-entry-has-been-reviewed-is-a-different-column-from-whether-it-has-been-classified)).
  It needed a column of its own rather than being read off either candidate already on the row:
  486 of the 893 seeded entries are unclassified, so that flag would bury the queue, and an approved
  entry stays `Origin.USER` for ever, so provenance never empties it. Correcting and merging follow.
- ~~**Finding entries that might be duplicates.**~~ **Built**
  ([ADR-053](07-decisions.md#adr-053-the-matcher-ranks-a-person-decides)) — a pure `MatchingEngine`,
  a sweep across the registry and a notification on each entry. It **ranks and never decides**: an
  import that acted on a resemblance would attach one food's allergens to another food's recipe.
  Accent folding in `resolve` is separate and *does* resolve, because `crème` and `creme` are one
  word written twice. Run against the shipped registry it found eleven real duplicate pairs,
  including a `pizza doug` typo in the seed data.
- ~~**Best-effort nutrition matching on creation.**~~ **Reconsidered, and answered differently.**
  The bullet assumed a source tree that could be asked for a row matching a new name. There is none:
  composition data is stored per registry entry, so the Swiss rows *are* the nine hundred generic
  foods, and "ask the source for a match" reduces to "find a resembling entry and borrow its
  figures". That is unsound in exactly the cases the matcher surfaces. Where two entries are the
  same food the right act is to **merge**, which already carries the figures across
  ([ADR-052](07-decisions.md#adr-052-merging-repoints-an-eaters-constraints-which-nothing-in-the-database-protects));
  copying instead would leave two entries claiming to be one food, which is the split merging exists
  to undo. Where they are a table variant, borrowing is simply wrong — baked pizza dough is 266 kcal
  and raw is 229.

  What was built instead is the honest part: a suggestion says **whether it carries figures this
  entry lacks**, so the cost of leaving a duplicate unmerged is stated rather than inferred. A
  genuine second source (Ciqual, CoFID, USDA) would reopen this, and that is a Phase 9 question about
  shipping more data.
- **The registry as an Academy page** — what an ingredient is, what it is called elsewhere, what it
  weighs, what it contains, what it can be swapped for. That is reference material, which is what an
  Academy is for.

Placed here rather than in Phase 6b because none of it blocks a first release: the guesses are
already conservative in the direction that matters — an unclassified allergen never claims a recipe
is safe.

### Where food sits

**Built.** A category tree, taken from the column the Swiss workbooks always carried and Quookly was
throwing away
([ADR-067](07-decisions.md#adr-067-where-a-food-sits-is-a-tree-taken-from-the-table-it-was-already-in)).
Trilingual for free, because the three editions publish it against identical row ids. It unblocked a
shopping list grouped by aisle and a registry that can be narrowed to one part of the shelf.

~~What is owed: a screen to correct it~~ **Built** — the entry screen carries the picker, so an admin
files what the seed could not. And the Academy's ingredient section is shelved by it, which is the
hierarchy the visual review asked for. What is still owed is that nothing places an ingredient an
import invents until a person does — the same gap this phase has for per-locale names on those rows,
and worth doing with them.

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
- ~~Record the language a recipe is written in~~ **Built** — read from `<html lang>` on import as a
  bare code (`de`, not `de-CH`), and taken from the cook's own language for anything written or
  composed here. Nobody is asked: somebody typing into a German screen is writing German.
  **Absent where nobody knows**, and not backfilled — guessing at the language of every recipe
  already stored would be inventing the one fact this exists to stop inventing.
- ~~`TranslationEngine`~~ **Built** — the same shape as `InterpretationEngine` pointed at a
  different question. Prose only: quantities, durations and temperatures are columns rendered per
  cook and ingredient names resolve through the registry, so a translation *cannot* change what a
  recipe asks for. The whole recipe in one round trip, because a step translated alone loses what
  the step before it established.
- ~~Translations stored beside the original, derived lazily on first request~~ **Built** — and the
  invalidation is the interesting part. A translation **records what it translated**
  ([ADR-064](07-decisions.md#adr-064-a-translation-records-what-it-translated-and-a-persons-words-are-not-re-derived)):
  a fingerprint of the source travels with it, and one that no longer matches is not used.
  Not a `stale` flag — a flag has to be set by every write path, and the one somebody forgets shows
  a cook instructions for a step that was rewritten. Editing a recipe needs to know nothing about
  translations.
- ~~The reader is told when the words are a machine's~~ **Built** — not optional. Prose a model
  produced, shown as the author's own words, is the failure
  [ADR-056](07-decisions.md#adr-056-a-generated-explanation-is-marked-unreviewed-and-never-an-input-to-a-judgement)
  exists to prevent one layer up, and here the author may be somebody the reader knows.
- ~~**A cook may correct a translation**, and a correction is never silently re-derived~~ **Built**
  — the screen puts the author's own words beside every field, and two things the decision implied
  turned out not to be in the code: `keep` let a model replace a person's translation, and a stale
  correction was being re-derived rather than the recipe being shown in its own language. Both are
  closed, and `translated_by_hand` says whose words a reader is looking at
  ([ADR-064](07-decisions.md#adr-064-a-translation-records-what-it-translated-and-a-persons-words-are-not-re-derived))
- **The interchange format carries a person's translations and not a machine's** — decided, not yet
  built
- Per-locale names for ingredients an import created, so a foreign import is as readable as a
  seeded one

Placed here rather than earlier because it is worth having only once there is a corpus worth
reading, and because it depends on nothing in Phase 9.

## Phase 9 — Self-hosting polish

**Goal:** someone other than us runs it.

- ~~Container image serving API and frontend from one artefact (NFR-2)~~ **Built** — a multi-stage
  build, non-root, with a healthcheck. Migrations run in the entrypoint rather than in the
  application's lifespan: an instance that migrates itself on every boot is one where two containers
  starting together race each other, and where a failed migration looks like a failed start-up.
  **Both the database and the pictures live under one `/data` volume**, which is what turns the
  two-things-to-back-up trap below into one thing to copy.
- ~~Compose files: standalone, with Ollama~~ **Built**, and Postgres deliberately not: persistence is
  SQLite at v1 (ADR-009, ADR-018), and shipping a compose file for a database the application does
  not support would be shipping a broken instance.
- ~~CI, and an image published to the GitHub Container Registry~~ **Built** — `check` runs the same
  `just check` a developer runs rather than a second definition of green, `e2e` runs the suite
  against the built bundle on the full Chromium, and `image` publishes for amd64 and arm64 because a
  self-hoster's box is as likely to be a Raspberry Pi as an x86 server.
- ~~An example `.env`~~ **Built** — every setting, including what an instance can and cannot do
  without a model, and why the signing key has no default.
- Backup, restore, and upgrade paths (UC-8.1). **Two things to copy, not one**: pictures live in a
  directory beside the database rather than inside it
  ([ADR-057](07-decisions.md#adr-057-the-academy-is-sections-of-pages-not-a-table-of-techniques)),
  so a backup that takes only the `.db` file restores an instance whose pages have holes in them
- Bulk import and export via CLI (UC-8.3)

### The CLI, deliberately later

The `cli/` project has one real command and exists mostly to prove the generated client works.
Everything recurring or bulk belongs there rather than in the FastAPI process — a scheduler inside
the application is a scheduler somebody has to operate. What is owed, as it has come up:

- **Collect orphaned pictures.** Nothing deletes media on its own: taking a picture off a page leaves
  the file, because a reference changing is not evidence that nobody wants the bytes. A command that
  lists what the database no longer refers to, and removes it when asked, is how that is reconciled.
- **Run the ingredient duplicate sweep** on a schedule, rather than somebody remembering to press the
  button ([ADR-053](07-decisions.md#adr-053-the-matcher-ranks-a-person-decides))
- **Recipe import** and **user approval and management**, which today need either the API or a screen
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
