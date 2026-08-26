# Quookly documentation

Design documentation for Quookly — a self-hostable cooking platform that gives you the recipe,
not the life story that precedes it.

## Reading order

| # | Document | What it answers |
| --- | --- | --- |
| 01 | [Vision](01-vision.md) | Why this exists, who it is for, what it refuses to be |
| 02 | [Requirements](02-requirements.md) | Actors, use cases, functional and non-functional requirements |
| 03 | [Volatility analysis](03-volatility-analysis.md) | What changes, and why the feature list is not the architecture |
| 04 | [Architecture](04-architecture.md) | The services, the layers, the call rules, the code layout |
| 05 | [Use case flows](05-use-case-flows.md) | How services interact to satisfy the requirements |
| 06 | [Domain model](06-domain-model.md) | The concepts and their relationships |
| 07 | [Decisions](07-decisions.md) | Design decisions, their rationale, and what is still open |
| 08 | [Roadmap](08-roadmap.md) | Delivery order and what "done" means per phase |
| 09 | [Installation](09-installation.md) | Running and self-hosting Quookly |
| 10 | [Development](10-development.md) | Working on Quookly, and contributing |
| 11 | [Design language](11-design-language.md) | How it should look and feel, and the theming system |

## Status legend

These documents describe the architecture. Most of it is now built. Every document marks status
explicitly:

- **Built** — exists in the repository today and passes `just check`
- **Partial** — scaffolded but incomplete
- **Planned** — designed here, not yet written

**[Phases 0 through 6b](08-roadmap.md) are complete**, and Phase 6b was the cut line for a first
release. A fresh instance walks an operator through creating the first admin; anybody else applies
for an account and an admin answers. A cook can author a recipe, import one from a URL with the
filler stripped, generate one from what is in the cupboard, read it at any yield in their own units
with nutrition and allergen verdicts attached, plan a week around who is coming, shop from a list net
of stock, and cook from the hob with timers and offline tolerance — after which the pantry knows what
was eaten.

**What is not built:** the [Academy and the correctable ingredient
registry](08-roadmap.md#phase-7--academy-and-the-registry) (Phase 7),
[community and gamification](08-roadmap.md#phase-8--community-and-engagement) (Phase 8),
[content translation](08-roadmap.md#phase-8b--reading-a-recipe-in-your-own-language) (Phase 8b), and
[self-hosting polish](08-roadmap.md#phase-9--self-hosting-polish) (Phase 9). Generating a recipe from
a photograph waits on a vision model, and looking a technique up from a step waits on the Academy.

## A note on these documents

Quookly exists because useful information gets buried in filler. The same standard applies here:
these documents state decisions and the reasoning behind them. If a section is not carrying
information a contributor needs, it should be deleted.
