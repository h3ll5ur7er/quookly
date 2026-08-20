# Vision

**Status: reference document. No code implied.**

## The problem

Searching for a recipe returns an essay. The technique you need is three scroll-lengths past a
childhood anecdote, the ingredient quantities assume a serving count you do not want, the units
are in a system you do not use, and the substitution you need — because someone at the table
cannot eat dairy — is not addressed at all.

The information a cook actually needs is small and highly structured:

- what to buy, in the quantities you will use
- what to do, in order, with timings and temperatures
- what it will do to you nutritionally
- what to change when the constraints change

Everything else is search engine optimisation.

## The mission

Quookly turns cooking information into structure, and keeps it structured. A recipe in Quookly is
never a wall of prose that happens to contain a list. It is a yield, an ingredient set, an ordered
set of steps, and the techniques those steps require — from which any presentation can be derived:
scaled, converted, adapted, costed, or read aloud.

Three consequences follow, and they are the whole product:

1. **Adaptation becomes computation.** Halving a recipe, converting cups to grams, making it
   dairy-free, or adjusting it for a toddler are operations on structure, not rewrites of prose.
2. **Planning becomes possible.** If recipes are structured and your pantry is known, a week of
   meals and the shopping list that fills the gaps can be derived rather than assembled by hand.
3. **Waste becomes visible.** Stock that is about to expire can drive what gets suggested, instead
   of being discovered at the back of the fridge.

## Who it is for

The primary user is a **cook who knows what they are doing, or wants to** — someone who values
precision, reads a recipe for its technique, and is irritated by imprecision. Professional
training is not assumed, but the product never dumbs down to avoid it.

Around that user sit the people they cook for: family members, regular guests, children, elderly
relatives — each with their own constraints. Quookly treats those people as first-class, because
the hardest part of cooking for others is not technique, it is constraint satisfaction.

## Principles

**Structure over prose.** Anything that can be a field is a field. Prose is a rendering, never the
source of truth.

**Self-hostable by default.** A family should be able to run Quookly on a small machine at home and
own their data, their recipes, and their model. Cloud services are an option, never a requirement.

**The model is a tool, not an authority.** Language models are excellent at turning mess into
structure and at proposing recipes. They are not a source of truth about whether food is safe for
a specific person. See the safety rule below.

**Bring your own intelligence.** Local inference (Ollama, vLLM) and hosted providers (OpenAI,
Anthropic, OpenRouter) are interchangeable. Nothing in the product may assume a specific one.

**Waste is a first-class metric.** Features that reduce food waste rank above features that add
engagement.

**Localisation is not translation.** `de_CH` is not `de_DE` with different strings — it implies
different units, different ingredient names, and different products on shelves.

## The safety rule

> **Dietary suitability and allergen conclusions are always computed from the structured ingredient
> set. They are never read out of model-generated prose.**

A model may propose a recipe and may claim it is nut-free. That claim is discarded. Suitability is
determined by evaluating the recipe's structured ingredients against the eater's structured
constraints. This is a correctness requirement with health consequences, and it constrains the
architecture: the component that generates content and the component that judges suitability must
be separate, and the judging component must not accept the generator's word for anything.

See [Suitability](03-volatility-analysis.md#v5-suitability) and
[ADR-006](07-decisions.md#adr-006-allergen-determination-is-structural).

## Non-goals

- **Not a social network.** Social features exist to circulate good recipes, not to maximise time
  in the app.
- **Not a grocery delivery integration.** Shopping lists are produced; ordering is out of scope.
- **Not a restaurant tool.** No costing per plate, no supplier management, no rota. The unit of
  work is a household meal.
- **Not a video platform.** Technique is documented as text, structure, and stills.
- **Not a nutrition authority.** Nutritional figures are estimates for informed choice, not medical
  advice, and are presented as such.
