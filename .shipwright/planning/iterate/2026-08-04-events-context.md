# P1.15 — Relevance-bounded iterate event context

- **Run ID:** `iterate-2026-08-04-p1-15-events-context`
- **Status:** implemented and verified
- **Type:** CHANGE (framework tooling)
- **Complexity:** medium
- **Risk flags:** `touches_io_boundary`, `touches_shared_infra`, `cross_component`

## Intent

Keep `shipwright_events.jsonl` unchanged as the append-only audit source while
replacing Iterate's normal full-log LLM startup read with a deterministic,
bounded, provenance-bearing event bundle selected after Repo Scout.

## Scope

### In scope

- One shared producer and schema for `.shipwright/agent_docs/area_catalog.json`.
- Greenfield Project/Plan seeding, brownfield Adopt seeding, Build realised-path
  refresh, and Iterate unmapped-path refresh through that producer.
- A disposable event index rebuilt solely from `shipwright_events.jsonl`.
- Compact, shadow, and explicit full modes; compact is the default.
- The pinned fail-soft ladder: current catalog, path ownership/changed files,
  then bounded recent/global events, with visible degradation and non-empty
  fallback whenever readable history exists.
- Query filters for area, changed file, event type and FR, deterministic order,
  provenance, hard event/token/string limits, explicit truncation, and hostile
  event-text handling.
- Per-run metrics JSONL and a regenerated operator Markdown report under
  `.shipwright/compliance/context-cost/`.
- Startup and phase documentation plus executable unit/integration coverage.

### Out of scope

- Changing, truncating, rewriting, or redirecting deterministic consumers of
  `shipwright_events.jsonl`.
- Decision-log retrieval, semantic/vector search, historical git backfill, or
  a cleanup item for the temporary observation artifacts.
- The unrelated local Claude read-tool batching experiment.

## Affected boundaries

- **Structured files:** area catalog, derived index, context bundle, metrics.
- **CLI:** catalog seed/refresh and event-context query/rebuild surfaces.
- **Plugin workflow:** Project, Plan, Adopt, Build, and Iterate instructions.
- **Prompt trust boundary:** event strings and repository paths are untrusted
  evidence, never agent instructions.

## Acceptance criteria

1. `event_context.py query` defaults to compact mode and returns no more than
   the requested event/token/string limits; output records source sequence,
   selection reason, source hash, coverage, fallbacks, and truncation counts.
2. Compact startup instructions run Repo Scout before the query and never tell
   the LLM to read the complete raw log; full mode is an explicit operator
   selection and shadow mode returns the compact payload while measuring full.
3. The shared catalog producer deterministically seeds greenfield requirements
   and planned architecture paths, seeds brownfield folders/manifests/workspaces
   and feature paths, refreshes realised paths, and reports/adds provisional
   mappings for unmapped Iterate paths.
4. A missing, stale, malformed, or unusable catalog visibly degrades through
   changed-file/path ownership and bounded recent/global events; readable
   history never produces an unexplained empty bundle.
5. Deleting the derived index and rebuilding it from an unchanged raw log and
   catalog yields byte-identical structured index content and query ordering.
6. Area, changed-file, FR, and event-type filters compose deterministically;
   overlapping area rules use exact match, longest static prefix, priority,
   then stable area ID precedence.
7. Hostile event text, control characters, instruction-shaped prose, hostile
   paths, and secret-like values remain escaped/redacted bounded JSON data and
   cannot alter the query command or bundle contract.
8. Query/index failure uses a visible bounded direct-log fallback; the result
   records the fallback and never silently expands to full or silently drops
   all readable history.
9. Every query writes one metrics line and regenerates an immediately readable
   report containing mode, full/selected counts, bytes and estimated tokens,
   query count, truncations, fallbacks, and reduction percentage; neither
   observation artifact is part of the documented startup inputs.
10. Existing event-log readers and append behavior remain unchanged, and an
    integration test proves catalog producer → index rebuild → compact query →
    metrics/report composition through the public CLIs.

## Verification (medium+)

- **Surface:** CLI
- **Runner:** `uv run shared/scripts/tools/event_context.py query` against an
  isolated fixture repository, plus the canonical suite runner.
- **Evidence path:** `.shipwright/runs/iterate-2026-08-04-p1-15-events-context/surface_verification.json`
- **AC-agent:** The CLI exits 0, emits a bounded compact bundle containing a
  relevant prior event, records visible fallback/truncation metadata, and
  writes both observation artifacts.
- **AC-user:** Optional: read the generated context-cost Markdown report and
  confirm the latest/rolling table is understandable without implementation
  knowledge.

## Confidence Calibration

- **Boundaries touched:** structured JSON contracts, filesystem writes, CLI,
  cross-plugin workflow instructions, prompt-data boundary.
- **Empirical probes run:** the canonical F0 runner completed GREEN across 18
  isolated test roots with 89% diff coverage; the public CLI surface gate ran
  both catalog-to-query integration scenarios; test-hygiene reported no
  findings. Integration fan-out was red in its parallel pass and green in the
  canonical isolated retry, recorded as `trg-c31bd693` rather than hidden.
- **Test Completeness Ledger:** AC 1, 4-8 are exercised by
  `shared/scripts/tests/test_event_context.py`; AC 2-3 and 9-10 are exercised
  by `integration-tests/test_event_context_workflow.py` plus the changed phase
  contract tests. Full, shadow, compact, catalog seeding/refresh, byte-stable
  rebuild, missing/stale/poisoned state, hard bounds, explicit truncation,
  direct-log fallback, and hostile event text all have executable evidence.
- **Confidence-pattern check:** depth is provided by failure and boundary unit
  cases, breadth by all affected plugin/root suites, and integration by the
  public producer -> index -> compact query -> metrics/report subprocess flow.

## Requirement impact

No adopted application FR changes. This is framework tooling governed by the
P1.15 action-unit and primary design brief; existing event-log behavior is an
explicit invariant.
