@AGENTS.md

## Quookly frontend

- Generated API client lives in `src/api/` — **never edit it**. Regenerate with `just frontend generate-openapi-client` (or `just openapi` from the repo root) after any backend API change.
- Import generated services through the `@api` path alias (`import { StatusService } from '@api'`), never via relative paths into `src/api/`.
- Component selector prefix is `app-`; place shared components under `src/app/core/`, routed feature areas under `src/app/features/` (lazy-loaded via `loadComponent`).
- Before finishing: `just frontend check` (lint + typecheck + test).
