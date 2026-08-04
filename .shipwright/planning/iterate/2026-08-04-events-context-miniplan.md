# Mini-plan — P1.15 relevance-bounded event context

- **Run ID:** `iterate-2026-08-04-p1-15-events-context`
- **Complexity:** medium
- **Change type:** framework tooling

## Files and work breakdown

1. Add shared area-catalog library and CLI.
   - Own schema validation, deterministic normalization, seed strategies,
     matching precedence, stale detection, atomic writes, and refresh reports.
   - Tests: greenfield, brownfield, overlap precedence, stale/missing/malformed,
     realised paths, and unmapped provisional mappings.
2. Add shared event-index/query library and CLI.
   - Stream the raw log into a minimal disposable index; select bounded events
     by changed files/areas/FRs/types plus recent/global safety fallback.
   - Enforce provenance, deterministic ordering, redaction/control stripping,
     string/event/token caps, explicit truncation, and visible failure states.
   - Tests: rebuild identity, all modes, bounds, fallbacks, hostile input,
     poisoned cache, missing/corrupt/empty log, and filter composition.
3. Add temporary measurement writer/report renderer.
   - One per-query line plus latest/rolling Markdown values; no startup reader.
   - Tests: required columns, rolling aggregation, full fallback counting.
4. Wire the public workflow.
   - Iterate: Repo Scout first, then compact query; document shadow and explicit
     full rollback; refresh unmapped paths.
   - Project/Plan/Adopt/Build: invoke the same catalog CLI at their artifact or
     completion boundary.
   - Update the hooks/pipeline read/write matrices and user guide.
5. Prove composition and non-regression.
   - Public-CLI integration scenario plus focused unit roots, canonical F0,
     Ruff, `verify_local.py`, reviewer cascade, finalization and delivery.

## Test strategy

- `shared/scripts/tests`: pure catalog, index, query, safety, metrics tests.
- `integration-tests`: one real subprocess flow across both shared CLIs.
- Plugin tests: contract assertions for the changed phase instructions and
  Adopt's seeded iterate-config shape only if configuration is extended.
- CLI surface verification runs an isolated fixture and records F0.5 evidence.

## Alternative considered

Putting relevance logic directly in Iterate was rejected because Project,
Plan, Adopt, Build, and Iterate would become competing schema writers. A shared
producer plus thin phase invocations gives one authority and makes the index
fully disposable without weakening the raw log's authority.
