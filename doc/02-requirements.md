# Requirements

**Status: all Planned unless marked otherwise.**

Requirements are recorded here as *what the system must do*. They are deliberately not a
decomposition of the system — see [Volatility analysis](03-volatility-analysis.md) for why the
architecture does not mirror this list.

## Actors

| Actor | Description |
| --- | --- |
| **Visitor** | Unauthenticated. Sees public recipes and the Academy. |
| **Cook** | Authenticated user. Owns recipes, plans, pantry, and profile. The primary actor. |
| **Eater** | A person a Cook cooks for — household member or regular guest. Has dietary constraints. Not an account. |
| **Contributor** | A Cook who adds Academy content (definitions, techniques, tips). |
| **Operator** | Runs a self-hosted instance. Uses the CLI. Not necessarily a Cook. |
| **Admin** | The first Cook created on a fresh instance, plus anyone they promote. Manages users and instance settings. |

An Eater is deliberately *not* a user account. Most people cooked for will never log in, and
requiring an account to record "Sofia cannot eat shellfish" would make the feature useless.

## Use cases

Use cases are grouped by the actor goal they serve. Each is satisfied by an *interaction of
services*, shown in [Use case flows](05-use-case-flows.md).

### UC-1 Obtain a recipe

| ID | Use case |
| --- | --- |
| UC-1.1 | Author a recipe by hand |
| UC-1.2 | Import a recipe from exported JSON |
| UC-1.3 | Import a recipe from a website URL, discarding narrative filler |
| UC-1.4 | Generate a recipe from a set of ingredients |
| UC-1.5 | Generate a recipe from a name, description, or tags |
| UC-1.6 | Generate a recipe from an uploaded photograph |
| UC-1.7 | Derive a variant of an existing recipe (dietary adaptation, substitution, scaling) |

UC-1.3 is the founding use case: the product exists because this is currently painful.

### UC-2 Understand a recipe

| ID | Use case |
| --- | --- |
| UC-2.1 | View a recipe scaled to an arbitrary yield |
| UC-2.2 | View quantities in the viewer's preferred unit per ingredient kind |
| UC-2.3 | View estimated nutrition per serving and per recipe |
| UC-2.4 | See whether a recipe is suitable for a named set of eaters, and why not |
| UC-2.5 | Look up an unfamiliar technique or term from within a recipe |

### UC-3 Find a recipe

| ID | Use case |
| --- | --- |
| UC-3.1 | Full-text search across recipes |
| UC-3.2 | Filter by tag, cuisine, time, difficulty, dietary suitability |
| UC-3.3 | Find recipes cookable from current pantry stock |
| UC-3.4 | Find recipes that consume stock nearing expiry |

### UC-4 Plan meals

| ID | Use case |
| --- | --- |
| UC-4.1 | Create a meal plan for a period, assigning recipes to slots |
| UC-4.2 | Declare which eaters attend each planned meal |
| UC-4.3 | Have the plan reject or flag meals unsuitable for attending eaters |
| UC-4.4 | Generate a shopping list for the plan, net of current stock |
| UC-4.5 | Record a planned meal as cooked, consuming the reserved stock |

### UC-5 Manage the pantry

| ID | Use case |
| --- | --- |
| UC-5.1 | Record stock received, with quantity and expiry |
| UC-5.2 | View current stock, with items nearing expiry surfaced |
| UC-5.3 | Adjust stock manually (used elsewhere, spoiled, miscounted) |
| UC-5.4 | Record waste, with reason |

### UC-6 Manage eaters and preferences

| ID | Use case |
| --- | --- |
| UC-6.1 | Register, authenticate, and manage an account |
| UC-6.2 | Define preferred unit per ingredient kind (powders in grams, liquids in millilitres, …) |
| UC-6.3 | Add regular guests and household members with dietary constraints |
| UC-6.4 | Set an eater's age band, so recipes can be adjusted for children, babies, or elderly |
| UC-6.5 | Set an eater's appetite multiplier, so portions match the person rather than the age band |

### UC-7 Participate

| ID | Use case |
| --- | --- |
| UC-7.1 | Publish a recipe publicly or keep it private |
| UC-7.2 | Follow another Cook and see their public recipes and shared plans |
| UC-7.3 | Rate and comment on recipes and shared plans |
| UC-7.4 | Contribute Academy content |
| UC-7.5 | Earn points and badges; view leaderboards filtered by period, category, and group |

### UC-9 Cook a recipe

Guided execution. The cook is standing up, hands busy, phone or tablet propped somewhere.

| ID | Use case |
| --- | --- |
| UC-9.1 | Start a cooking session for a recipe and a chosen set of eaters |
| UC-9.2 | Work through mise-en-place: what to prep, in what quantity, grouped sensibly |
| UC-9.3 | Be guided through the steps one at a time, with progress preserved |
| UC-9.4 | Start, pause, and reset a timer belonging to a step |
| UC-9.5 | Look up an unfamiliar term from the current step without losing place |
| UC-9.6 | Complete the session, consuming the stock the meal used |
| UC-9.7 | Resume an interrupted session, including on a different device |
| UC-9.8 | Abandon a session without consuming stock |

UC-9.7 is not a nicety. Cooking is interrupted constantly, phones lock, and a session that dies when
the screen does is worse than a printed page.

### UC-10 Get started

| ID | Use case |
| --- | --- |
| UC-10.1 | On a fresh instance, create the first admin user |
| UC-10.2 | As a new user, be guided through setting up eaters, constraints, units, and locale |
| UC-10.3 | See what is still missing from the setup, and resume it later |
| UC-10.4 | Start with a usable ingredient registry and a set of starter recipes, not an empty app |
| UC-10.5 | As an admin, manage users and instance settings |

UC-10.4 matters more than it sounds. An empty recipe app is indistinguishable from a broken one, and
a cook with nothing to look at has no reason to return.

### UC-8 Operate an instance

| ID | Use case |
| --- | --- |
| UC-8.1 | Install, configure, back up, and upgrade a self-hosted instance |
| UC-8.2 | Configure the inference backend (local or hosted, with credentials) |
| UC-8.3 | Bulk import and export recipe data |
| UC-8.4 | Inspect instance health |

UC-8.4 is **Built** — `/api/v1/status` exists and the CLI can query it.

## Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | A recipe is stored as structured data: yield, ingredient set, ordered steps, technique references, timings, equipment. Prose is derived. |
| FR-2 | Any quantity may be rendered in any compatible unit, using ingredient-specific density where mass/volume conversion is required. |
| FR-3 | Dietary suitability is computed from the structured ingredient set and never taken from generated text. |
| FR-4 | Every ingredient resolves to an entry in a shared ingredient registry carrying nutritional data and locale-specific names. |
| FR-5 | Recipes are private by default; publishing is explicit. |
| FR-6 | A meal plan reserves stock; cooking consumes it. Deleting a plan releases the reservation. |
| FR-7 | A shopping list is the plan's requirement net of unreserved stock, aggregated per ingredient. |
| FR-8 | Inference provider and model are configuration, not code. At least one local and one hosted provider must be supported. |
| FR-9 | Generated and imported recipes are validated before persistence; validation failure is reported, never silently corrected. |
| FR-10 | All user-facing text is localisable; `en_GB`, `de_CH`, and `fr_CH` ship at v1. |
| FR-11 | Recipe data is exportable in a documented JSON format and re-importable without loss. |
| FR-12 | Points and badges are awarded by rules that can change without migrating historical activity. |

| FR-13 | A cooking session is server-side state, resumable on any device the cook is signed in on. |
| FR-14 | Timers are derived from recipe structure and controlled by the cook. Timer state survives navigation, device change, and app restart. |
| FR-15 | Onboarding progress is derived from profile data, never stored as a completion flag. "Declared none" is distinguishable from "not answered". |
| FR-16 | A fresh instance allows exactly one unauthenticated admin bootstrap. The path closes permanently once any user exists. |
| FR-17 | A fresh instance ships a locale-appropriate ingredient registry and starter recipes, marked as seeded, and upgradable without overwriting user edits. |
| FR-18 | Each eater carries an appetite multiplier applied when portions are computed. |
| FR-19 | Completing a cooking session consumes reserved stock; abandoning one releases it. |

FR-11 matters more than it looks: it is the guarantee that self-hosters are not trapped, and it
makes the import path (UC-1.2) and the export path the same contract.

## Non-functional requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-1 | Self-hostable on modest hardware | Runs on 2 cores / 2 GB RAM, excluding local inference |
| NFR-2 | Single-artefact deployment | One container serves API and frontend |
| NFR-3 | Zero-dependency default datastore | SQLite works out of the box; Postgres is opt-in |
| NFR-4 | Interactive responsiveness | Non-inference API calls respond in under 300 ms at p95 on target hardware |
| NFR-5 | Inference is never on the critical path for browsing | Generation is explicit and asynchronous where slow |
| NFR-6 | Data ownership | Full export without the application running |
| NFR-7 | Accessibility | WCAG AA; passes AXE checks |
| NFR-8 | Offline-tolerant reading | A viewed recipe remains readable without connectivity |
| NFR-9 | Type safety end to end | Strict mypy, strict Angular templates, generated API clients |
| NFR-10 | Architectural conformance is enforced | Layer violations fail the build, not review |
| NFR-11 | Mobile-first | Every flow usable one-handed at a 360 px viewport; phone and tablet are the primary targets |
| NFR-12 | Cooking mode is usable with busy hands | Large touch targets, screen wake lock held, legible at arm's length |
| NFR-13 | Offline tolerance where it matters | The active recipe, the running session, and the shopping list remain usable without connectivity |
| NFR-14 | Behaviour changes arrive test-first | Every behavioural change lands with a test written before the implementation |

NFR-10 is not aspirational — see [ADR-008](07-decisions.md#adr-008-enforce-the-call-rules-with-import-linter).

NFR-11 is a correction to the obvious assumption. The laptop is where Quookly gets *built*; the
phone in a shop and the tablet on a worktop are where it gets *used*. Designing for the desktop and
adapting downward produces exactly the cramped experience the product is meant to replace — so the
narrow viewport is the design target and the wide one is the adaptation.

NFR-14 is a process requirement rather than a property of the running system, recorded here because
it is not negotiable — see [ADR-017](07-decisions.md#adr-017-test-driven-development-with-per-unit-quality-gates).

## Constraints

- Python 3.12+, FastAPI, uv; Angular 21, npm via nvm; commands encapsulated in justfiles.
- The backend is the sole author of the API contract; clients are generated from it.
- The architecture follows the iDesign Method as stated in the root `README.md`.
- No paid third-party service may be required to run the product.

## Out of scope for v1

Grocery ordering, meal-kit integration, barcode scanning, multi-tenant hosting with billing,
recipe video, and voice control. Each is plausible later; none may shape the v1 architecture.
