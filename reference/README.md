# Reference data

The published documents the shipped seed data is derived from, kept here rather than
downloaded on demand.

**Why they are in the repository.** Two reasons, and the second is the one that decided it.

They are the provenance of every nutrition figure Quookly displays. `backend/seed/*.json`
is derived data; this is what it was derived *from*, and a number on a cook's screen should
be traceable to a published row in a document somebody can open
([ADR-045](../doc/07-decisions.md#adr-045-composition-data-is-tried-in-a-configured-order-nearest-table-first)).

And the download links do not survive. The Swiss workbook lives at a path containing the
month it was published, so the URL below will be dead the next time the FSVO releases an
edition. A build step that fetched it would work until it quietly did not.

Each file's licence permits redistribution with attribution, which is why the credit is
carried per source and shown on every recipe that uses it (FR-20).

## What is here

### `swiss-food-composition-database.xlsx`

| | |
| --- | --- |
| **Dataset** | Swiss Food Composition Database, V7.1 |
| **Publisher** | Federal Food Safety and Veterinary Office (FSVO) |
| **Terms** | ["Open use. Must provide the source."](https://opendata.swiss/en/terms-of-use) — commercial use permitted, attribution mandatory |
| **Retrieved** | 2026-08-22, from `https://naehrwertdaten.ch/en/downloads/` |
| **SHA-256** | `323bae2eecd639d2c3b3bf3797d30b1426ccb0253fb62810f522778b38089196` |

1,216 generic foods with the nutrients an EU label declares, plus densities. Read by
[`backend/seed/swiss.py`](../backend/seed/swiss.py), which checks the digest above before
it reads anything: derived data should say which document it came from, not merely which
*kind* of document.

## Refreshing one

Replace the file, update its retrieval date and digest here, and re-run the builder. The
digest check will fail first and say so, which is the point — a refreshed table is a
changed input, and it should be a thing somebody did rather than a thing that happened.

    cd backend && uv run --with openpyxl python seed/swiss.py

Then read the diff on `backend/seed/nutrition.swiss.json`. A publisher revising a figure is
news worth looking at.
