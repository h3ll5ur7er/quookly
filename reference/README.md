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

### `swiss-food-composition-database.de.xlsx` and `.fr.xlsx`

| | |
| --- | --- |
| **Dataset** | The same database, V7.1, German and French editions |
| **Retrieved** | 2026-08-22, from `https://naehrwertdaten.ch/de/downloads/` and `/fr/downloads/` |
| **SHA-256 (de)** | `f4bb854944ef811f9b8463984389f8121e73278c4fd24fc3e8d16336cb711270` |
| **SHA-256 (fr)** | `1692aa241728f25d4823a6c97bb36c393f7f64173a00a8ed4175b1bf926a5405` |

**Why three copies of one database.** The row ids are identical across all three editions,
which is what makes a trilingual registry possible without translating anything ourselves:
row 368 is `Onion, raw`, `Zwiebel, roh` and `Oignon, cru`, and all three become names for
one entry. A cook importing a German recipe resolves *Zwiebel* against the same ingredient
an English one reaches by *onion* (FR-10).

Without them, [`backend/seed/generic.py`](../backend/seed/generic.py) could still build the
registry — and every one of its nine hundred entries would be named in English only, so a
German recipe would resolve nothing and invent nine hundred duplicates nobody has
classified. That is the failure this costs two megabytes to avoid.

## Refreshing one

Replace the file, update its retrieval date and digest here, and re-run the builders. The
digest check will fail first and say so, which is the point — a refreshed table is a
changed input, and it should be a thing somebody did rather than a thing that happened.

    cd backend && uv run --with openpyxl python seed/swiss.py
    cd backend && uv run --with openpyxl python seed/generic.py

Then read the diff on `backend/seed/nutrition.swiss.json` and
`backend/seed/generic-foods.json`. A publisher revising a figure is news worth looking at,
and so is one withdrawing a food: an entry that disappears from the built file stays in a
running instance's registry, because a cook may have used it.
