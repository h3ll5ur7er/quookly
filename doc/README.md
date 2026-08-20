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

## Status legend

These documents describe a target architecture. Almost none of it is built yet. Every document
marks status explicitly:

- **Built** — exists in the repository today and passes `just check`
- **Partial** — scaffolded but incomplete
- **Planned** — designed here, not yet written

As of this writing the repository contains the template scaffold plus a single `/api/v1/status`
endpoint. Everything else is **Planned**.

## A note on these documents

Quookly exists because useful information gets buried in filler. The same standard applies here:
these documents state decisions and the reasoning behind them. If a section is not carrying
information a contributor needs, it should be deleted.
