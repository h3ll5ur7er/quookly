# Use case flows

**Status: Planned.**

> Requirements are not represented by subsystems, but by the interaction of services.

These sequences show how the services in [Architecture](04-architecture.md) collaborate to satisfy
the use cases in [Requirements](02-requirements.md). They are the proof that the decomposition
works: if a requirement cannot be satisfied by services calling each other within the
[call rules](04-architecture.md#call-rules), the decomposition is wrong.

Utilities are omitted unless they carry the point of the diagram.

## UC-1.3 Import a recipe from a URL

The founding use case. A cook pastes a link to a recipe buried in a thousand words of preamble.

```mermaid
sequenceDiagram
  actor Cook
  participant API as "API route"
  participant RM as "RecipeManager"
  participant WEB as "WebContentAccess"
  participant IE as "InterpretationEngine"
  participant MOD as "ModelAccess"
  participant ING as "IngredientAccess"
  participant NE as "NutritionEngine"
  participant RCA as "RecipeAccess"
  participant BUS as "EventBus"

  Cook->>API: import recipe from URL
  API->>RM: import_from_url(url, cook)
  RM->>WEB: fetch_readable(url)
  WEB-->>RM: readable content
  RM->>IE: interpret(content)
  IE->>MOD: complete_structured(prompt, schema)
  MOD-->>IE: structured candidate
  IE-->>RM: canonical recipe draft
  RM->>ING: resolve_by_name(each ingredient)
  ING-->>RM: registry entries
  RM->>NE: profile(recipe, entries)
  NE-->>RM: nutrient profile
  RM->>RCA: store(recipe, provenance=url)
  RCA-->>RM: recipe id
  RM->>BUS: publish RecipeImported
  RM-->>API: recipe
  API-->>Cook: structured recipe
```

Three things worth noting:

- `ModelAccess` is asked for *structured* output against a schema. The model fills a shape; it does
  not author the shape.
- Ingredient resolution happens against the registry, not against model output. An unresolvable
  ingredient is reported (FR-9), never invented.
- Nothing here knows which provider served the completion.

## UC-1.4 Generate a recipe from pantry stock

```mermaid
sequenceDiagram
  actor Cook
  participant API as "API route"
  participant RM as "RecipeManager"
  participant PAN as "PantryAccess"
  participant EAT as "EaterAccess"
  participant GE as "GenerationEngine"
  participant MOD as "ModelAccess"
  participant SE as "SuitabilityEngine"
  participant ING as "IngredientAccess"
  participant RCA as "RecipeAccess"

  Cook->>API: generate recipe from what I have
  API->>RM: generate_from_pantry(cook, eaters)
  RM->>PAN: expiring_before(date)
  PAN-->>RM: stock items
  RM->>EAT: constraints_for(eaters)
  EAT-->>RM: constraint set
  RM->>GE: compose(stock, constraints)
  GE->>MOD: complete_structured(prompt, schema)
  MOD-->>GE: candidate recipe
  GE-->>RM: canonical recipe draft
  RM->>ING: resolve_by_name(each ingredient)
  ING-->>RM: registry entries
  RM->>SE: evaluate(recipe, constraints)
  SE-->>RM: verdict with reasons
  alt unsuitable
    RM-->>API: rejected with reasons
  else suitable
    RM->>RCA: store(recipe, provenance=generated)
    RM-->>API: recipe
  end
  API-->>Cook: recipe or explained rejection
```

**This is the safety rule in mechanical form.** The constraints are passed *into* generation to
improve the odds, and then the result is independently evaluated by `SuitabilityEngine` against the
resolved structured ingredients. A model asserting "this is dairy-free" carries no weight; the
verdict comes from the ingredient set. Generation and judgement are separate services precisely so
that the judgement cannot be talked out of its conclusion.

## UC-4.1 to UC-4.4 Plan a week with guests, and shop for it

```mermaid
sequenceDiagram
  actor Cook
  participant API as "API route"
  participant PLM as "PlanningManager"
  participant EAT as "EaterAccess"
  participant PE as "PlanningEngine"
  participant RCA as "RecipeAccess"
  participant SE as "SuitabilityEngine"
  participant PAN as "PantryAccess"
  participant RE as "ReplenishmentEngine"
  participant ME as "MeasureEngine"
  participant PLA as "PlanAccess"

  Cook->>API: plan next week, Sofia attends Thursday
  API->>PLM: build_plan(period, slots, attendance)
  PLM->>EAT: constraints_for(attending eaters)
  EAT-->>PLM: constraints per slot
  PLM->>RCA: list_for_cook(cook)
  RCA-->>PLM: candidate recipes
  PLM->>PE: propose(slots, candidates, constraints)
  PE-->>PLM: proposed assignments
  PLM->>SE: evaluate(each assignment, slot constraints)
  SE-->>PLM: verdicts
  PLM->>PLA: store_plan(assignments)
  PLM->>PAN: reserve(requirements, plan)
  PAN-->>PLM: reserved and shortfall
  PLM->>RE: net(requirements, shortfall)
  RE->>ME: convert(quantities, shopping units)
  ME-->>RE: converted quantities
  RE-->>PLM: aggregated shopping list
  PLM-->>API: plan and shopping list
  API-->>Cook: week plan and list
```

The plan reserves rather than consumes ([ADR-004](07-decisions.md#adr-004-plans-reserve-stock-cooking-consumes-it)).
The shopping list is derived from the *shortfall* the reservation reports, so it is correct by
construction rather than by a second calculation that could disagree.

Note `ReplenishmentEngine` calling `MeasureEngine` — an Engine calling an Engine, permitted by the
call rules. Shopping units differ from cooking units: a recipe wants 150 g of butter, a shop sells
250 g blocks.

## UC-9 Cooking mode, start to finish

Two flows: opening a session, and completing it. Together they replace what used to be a single
"mark as cooked" action, and they are where the event bus earns its keep.

### UC-9.1 and UC-9.2 Start a session and get the mise-en-place

```mermaid
sequenceDiagram
  actor Cook
  participant API as "API route"
  participant CKM as "CookingManager"
  participant RCA as "RecipeAccess"
  participant EAT as "EaterAccess"
  participant ING as "IngredientAccess"
  participant ME as "MeasureEngine"
  participant EXE as "ExecutionEngine"
  participant SES as "CookingSessionAccess"

  Cook->>API: cook this, for these four people
  API->>CKM: start_session(recipe id, eaters)
  CKM->>RCA: fetch(recipe id)
  RCA-->>CKM: canonical recipe
  CKM->>EAT: constraints_for(eaters)
  EAT-->>CKM: constraints and appetite multipliers
  CKM->>ING: density_for(ingredients)
  ING-->>CKM: densities
  CKM->>ME: render(recipe, yield=sum of multipliers, preferences, densities)
  ME-->>CKM: scaled recipe
  CKM->>EXE: plan(scaled recipe)
  EXE-->>CKM: mise-en-place groups, ordered steps, timer specs
  CKM->>SES: open_session(plan)
  SES-->>CKM: session
  CKM-->>API: session with mise-en-place
  API-->>Cook: prep list, then step one
```

The yield is the **sum of the attending eaters' appetite multipliers**, not the head count (FR-18).
Four adults where one eats half portions is 3.5, and the mise-en-place quantities follow.

`ExecutionEngine` receives an already-scaled recipe. It never scales anything itself — that is V4
and lives in `MeasureEngine`. Keeping the split means appetite handling has exactly one
implementation, used identically by planning, shopping, and cooking.

### UC-9.6 Complete the session

```mermaid
sequenceDiagram
  actor Cook
  participant API as "API route"
  participant CKM as "CookingManager"
  participant SES as "CookingSessionAccess"
  participant BUS as "EventBus"
  participant PNM as "PantryManager"
  participant PAN as "PantryAccess"
  participant EGM as "EngagementManager"
  participant SCE as "ScoringEngine"
  participant COM as "CommunityAccess"

  Cook->>API: done
  API->>CKM: complete_session(session id)
  CKM->>SES: close_session(completed)
  CKM->>BUS: publish MealCooked
  CKM-->>API: session summary
  API-->>Cook: confirmation
  BUS-->>PNM: MealCooked
  PNM->>PAN: consume(reservation)
  BUS-->>EGM: MealCooked
  EGM->>SCE: score(event)
  SCE-->>EGM: points and badge awards
  EGM->>COM: award(cook, points, badges)
```

`CookingManager` publishes a fact and returns; the cook is not kept waiting on stock accounting or
scoring. `PantryManager` still owns inventory truth (V9) and `EngagementManager` still owns scoring
(V11) — neither knows cooking mode exists, and cooking mode knows nothing of either.

Abandoning a session (UC-9.8) publishes `SessionAbandoned` instead, which releases the reservation
without consuming it. The distinction is the reason abandonment is a first-class outcome rather than
a timeout: stock that was never cooked must come back.

## UC-2.1 and UC-2.2 View a recipe scaled and in preferred units

```mermaid
sequenceDiagram
  actor Cook
  participant API as "API route"
  participant RM as "RecipeManager"
  participant RCA as "RecipeAccess"
  participant EAT as "EaterAccess"
  participant ING as "IngredientAccess"
  participant ME as "MeasureEngine"

  Cook->>API: show recipe for 6, my units
  API->>RM: present(recipe id, yield=6, cook)
  RM->>RCA: fetch(recipe id)
  RCA-->>RM: canonical recipe
  RM->>EAT: unit_preferences_for(cook)
  EAT-->>RM: preferences per ingredient kind
  RM->>ING: density_for(ingredients)
  ING-->>RM: densities
  RM->>ME: render(recipe, yield=6, preferences, densities)
  ME-->>RM: scaled and converted recipe
  RM-->>API: presented recipe
  API-->>Cook: recipe as requested
```

`MeasureEngine` receives densities and preferences as arguments rather than fetching them. That is
what keeps it pure and exhaustively testable — the same property that matters most for
`SuitabilityEngine`. Gathering the inputs is sequencing, and sequencing is the manager's job.

## UC-3.4 Find recipes that use what is about to expire

```mermaid
sequenceDiagram
  actor Cook
  participant API as "API route"
  participant RM as "RecipeManager"
  participant PAN as "PantryAccess"
  participant EAT as "EaterAccess"
  participant RKE as "RankingEngine"
  participant IDX as "SearchIndexAccess"
  participant SE as "SuitabilityEngine"

  Cook->>API: what should I cook this week
  API->>RM: suggest_from_stock(cook, household)
  RM->>PAN: expiring_before(date)
  PAN-->>RM: urgent stock
  RM->>EAT: constraints_for(household)
  EAT-->>RM: constraints
  RM->>RKE: rank(urgent stock, coverage, urgency)
  RKE->>IDX: query(ingredients of urgent stock)
  IDX-->>RKE: candidate recipes
  RKE-->>RM: ordered recipes
  RM->>SE: evaluate(top candidates, constraints)
  SE-->>RM: verdicts
  RM-->>API: ranked suggestions
  API-->>Cook: ranked suggestions
```

Waste reduction as a ranking input rather than a feature bolted on: urgency is a signal into
`RankingEngine`, which is where V10 already lives.

## UC-10.1 Claiming a fresh instance

**Built.** The first flow in the system to exist rather than be designed.

```mermaid
sequenceDiagram
  actor Operator
  participant API as "API route"
  participant ACM as "AccountManager"
  participant CKA as "CookAccess"
  participant SEC as "Security"

  Operator->>API: does this instance need an admin
  API->>ACM: bootstrap_required()
  ACM->>CKA: any_registered()
  CKA-->>ACM: false
  ACM-->>API: required
  API-->>Operator: yes, claim it
  Operator->>API: create the first admin
  API->>ACM: bootstrap_admin(registration)
  ACM->>CKA: any_registered()
  CKA-->>ACM: still false
  ACM->>SEC: hash_password(password)
  SEC-->>ACM: hash
  ACM->>CKA: register(email, name, hash, is_admin=true)
  CKA-->>ACM: cook
  ACM->>SEC: issue_token(cook)
  SEC-->>ACM: token
  ACM-->>API: authenticated
  API-->>Operator: signed in as admin
```

The window closes against **any** account, not just an admin one — otherwise an instance somebody
had already registered on could still be claimed by the next visitor. A second attempt is a 409,
not a crash.

Note where the work sits. `Security` hashes and signs but never touches storage, because a utility
that reaches into a layer stops being usable by all of them. `CookAccess` stores but decides
nothing. The manager owns only the order.

## UC-10.2 and UC-10.3 Onboarding a new cook

```mermaid
sequenceDiagram
  actor NewCook
  participant API as "API route"
  participant RM as "RecipeManager"
  participant EAT as "EaterAccess"
  participant OBE as "OnboardingEngine"

  NewCook->>API: signed up, what now
  API->>EAT: fetch_cook(principal)
  EAT-->>API: profile, eaters, preferences
  API->>OBE: next_step(profile state)
  OBE-->>API: missing items and the next step
  API-->>NewCook: set up your household
  NewCook->>API: add eaters and constraints
  API->>EAT: store eaters and constraints
  API->>OBE: next_step(updated state)
  OBE-->>API: remaining items
  API-->>NewCook: set your preferred units
  NewCook->>API: preferences
  API->>EAT: store unit preferences
  API->>OBE: next_step(updated state)
  OBE-->>API: setup complete
  API->>RM: suggest_from_seed(cook)
  RM-->>API: starter recipes
  API-->>NewCook: here is your kitchen
```

Nothing stores "step 2 of 4 complete". `OnboardingEngine` reads the profile and derives what is
missing ([ADR-014](07-decisions.md#adr-014-onboarding-progress-is-derived-not-stored)), which is why
UC-10.3 — resume later, see what is outstanding — needs no extra machinery, and why a cook who
deletes all their eaters is correctly told their household is unset again.

The last exchange is UC-10.4 doing its job: the new cook lands on seeded recipes rather than an
empty list.

## Reading these diagrams

Every arrow crosses a layer boundary downward or stays within the permitted set. No Manager appears
in another Manager's diagram, no Engine calls upward, and no Client reaches Resource Access. Where
an engine needs an external capability it owns — `RankingEngine` over the index, `InterpretationEngine`
over the model — it calls Resource Access itself, which the rules permit.

If a future flow cannot be drawn under these constraints, that is a signal about the decomposition,
not about the rules. Return to [the volatility analysis](03-volatility-analysis.md) and ask what was
missed.
