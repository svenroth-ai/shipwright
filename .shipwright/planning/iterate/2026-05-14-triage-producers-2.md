# Iterate Spec: triage-producers-2

- **Run ID:** iterate-2026-05-14-triage-producers-2
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal

Wire the remaining triage producers (security, performance, F0.5, drift)
into the established `append_triage_item_idempotent` pattern from
Iterate 1a (ADR-046). Defer the CI producer — no autonomous data source
today.

## Acceptance Criteria

- [ ] **AC-1 — Security findings producer**: In
  `plugins/shipwright-security/scripts/tools/generate_security_report.py`,
  after `findings` (scanner + prompt-injection) is consolidated and
  before report rendering, emit one triage item per finding via
  `append_triage_item_idempotent`:
  - `source="security"`
  - severity = the scanner's severity verbatim (`critical|high|medium|low|info`);
    unrecognized values fall back to `"medium"` (conservative — never
    raise into the consolidation path)
  - `kind="bug"` for `critical|high`, `"improvement"` for `medium|low|info`
  - `title=f"[{tool}] {check_id}: {summary[:80]}"` capped to 160 chars
  - `detail` = file:line + description + suggested-fix when present
  - `evidence_path` = relative path to the SARIF / JSON report when known
  - `dedup_key=f"{tool}:{check_id}:{file}:{line}"`
  - `match_commit=True`, `window_seconds=24*3600` (daily re-flag)
  - Best-effort: per-item exceptions logged to stderr, never block the
    report. Skipped entirely when `findings == []`.

- [ ] **AC-2 — Performance budget producer**: In
  `plugins/shipwright-test/scripts/lib/performance_check.py` `main()`,
  after `success = evaluate_gate(...)` and before exit, emit one triage
  item per failed sub-check (Lighthouse score, Lighthouse LCP, bundle
  size) via `append_triage_item_idempotent`:
  - `source="performance"`
  - severity = `"high"` if the metric is more than 10% over budget,
    else `"medium"`. Overage is measured against budget direction:
    `(budget - actual) / budget` for `min_score` (higher better),
    `(actual - budget) / budget` for `lcp_max_ms` and `max_kb_gz`
    (lower better).
  - `kind="improvement"`
  - `dedup_key=f"perf:{metric}:{page}"` where metric ∈
    `{"score", "lcp", "bundle"}` and `page` = the relative path of the
    `--dev-url` (e.g. `"/"`, `"/dashboard"`) for Lighthouse-driven
    metrics, or `"global"` for `bundle`
  - `match_commit=True`, `window_seconds=24*3600`
  - Skipped entirely when `success=True` (no failed checks) or when the
    sub-check is skipped/skipped-due-to-config. NEVER raises; emission
    is best-effort.

- [ ] **AC-3 — CI failure producer: DEFERRED.** Documented in the
  iterate ADR + `docs/triage-inbox.md` under a new "Deferred producers"
  sub-section. No code added, no stub. Reason: no autonomous data
  source for CI state locally; GitHub webhook integration is out of
  scope.

- [ ] **AC-4 — F0.5 fail-closed producer**: In
  `shared/scripts/surface_verification.py` `main()`, after
  `verify_surface()` returns and BEFORE `sys.exit(exit_code)`, emit one
  triage item per non-zero exit via `append_triage_item_idempotent`:
  - `source="f0.5"`
  - `severity="critical"`, `kind="bug"`
  - Condition mapping:
    - `EXIT_ZERO_TESTS` (2) → `condition="tests_zero"`
    - `EXIT_RUNNER_FAILED` (3) → `condition="exit_nonzero"`
    - `EXIT_NONE_WITHOUT_JUSTIFICATION` (4) → `condition="surface_none_no_just"`
    - `EXIT_INVALID_ARGS` (1) → NOT emitted. Config-error (unknown
      surface name), not a substantive fail-closed.
  - `dedup_key=f"f0.5:{run_id}:{surface}:{condition}"`
  - `match_commit=True`, `window_seconds=24*3600`
  - Scope clarification: the handoff enum lists a fourth condition
    name `"missing_block"`. That condition is detected POST-COMMIT in
    `check_surface_verification()` in
    `shared/scripts/tools/verifiers/iterate_checks.py`, NOT in
    `surface_verification.py` (which IS the writer of the block — it
    can't detect its own absence). The `"missing_block"` enum value is
    reserved for a future iterate that adds the audit-side producer
    in `iterate_checks.py`. This iterate ships only the 3 runtime-fail
    producers in `surface_verification.py`. Locked decision; flagged
    in the iterate ADR.
  - Best-effort: triage emission failure must NOT change the exit code
    (F0.5 still STOPs the iterate via its own exit semantics).

- [ ] **AC-5 — Drift detection producer**: Two emission sites, same
  schema:
  - `shared/scripts/hooks/check_drift.py` `main()`: after the
    timestamp + content warnings list is built and before the
    SessionStart hookSpecificOutput is printed, emit one triage item
    per individual finding via `append_triage_item_idempotent`.
  - `shared/scripts/artifact_sync.py` `detect_drift()`: when
    `drift_detected=True`, emit one triage item per affected mapping
    via `append_triage_item_idempotent`.
  - `source="drift"`, `severity="medium"`, `kind="maintenance"`
  - `dedup_key=f"drift:{file}:{kind}"` where `kind ∈
    {"timestamp", "content", "artifact"}` and `file` is the affected
    path (`CLAUDE.md`, the structure entry, or the diff'd file)
  - `match_commit=False`, `window_seconds=None` — same shape as
    compliance: a drift finding stays as ONE triage item indefinitely
    until the operator promotes/dismisses or the drift resolves.
  - Best-effort: per-item exception logged to stderr; the SessionStart
    hook MUST still exit 0 (informational only — never block the
    session).

- [ ] **AC-6 — Drift tests**:
  - `shared/tests/test_security_triage_emit.py`
  - `shared/tests/test_performance_triage_emit.py`
  - `shared/tests/test_f0_5_triage_emit.py`
  - `shared/tests/test_drift_triage_emit.py` (covers both producer
    sites in one file — they share the same dedup semantics)
  - Each test importlib-loads its producer module, feeds synthetic
    findings (via direct function call or via subprocess-style stdin),
    and asserts `read_all_items(tmp_path)` contents. Mirrors
    `test_phase_quality_triage_emit.py` from iterate-1a.

- [ ] **AC-7 — Documentation**:
  - `docs/triage-inbox.md`: extend the Producers table with one row
    per new source (security, performance, f0.5, drift). Add a
    "Deferred producers" sub-section explaining the CI-producer
    deferral.
  - `docs/hooks-and-pipeline.md`: update the artifact-write matrix to
    note the four new producer sites that write to
    `.shipwright/triage.jsonl`.

## Affected FRs

This monorepo doesn't carry `shipwright_sync_config.json` with
FR-mappings (only `shipwright_run_config.json` + the adopted-baseline
single split). FR-coverage: producer wiring extends the FR covered by
Iterate 1a's ADR-046 (Triage Inbox Pattern) — no new FR row is added.
Iterate ADR (new) records the producer additions; the spec file
`.shipwright/planning/iterate/2026-05-11-triage-inbox-1a.md` already
documents the pattern.

## Out of Scope

- CI failure producer — explicitly deferred (handoff lock, AC-3 above)
- The `missing_block` audit-side F0.5 producer in `iterate_checks.py`
  — reserved for a future iterate (AC-4 scope clarification)
- Changing the iterate-1a producer pattern (decisions locked)
- Adding new mapping entries to `DOMAIN_FROM_SOURCE` — handoff says
  "all others → engineering" (compliance is the only special case)
- Compaction of `.shipwright/triage.jsonl` — tracked as future work
  from iterate-1a, NOT this iterate
- Performance budget runner construction — the runner already exists at
  `plugins/shipwright-test/scripts/lib/performance_check.py`. Handoff
  branch "if doesn't exist, stub it" is N/A.
- Drift detection logic changes — only the emission glue, not the
  detector

## Design Notes

n/a — no UI changes; this is producer wiring.

## Affected Boundaries

Triage `.shipwright/triage.jsonl` is the producer/consumer boundary the
new emitters write to. Tested via real round-trip (producer writes →
file-on-disk → `read_all_items` reads) in each per-producer test file,
plus the existing `test_triage_storage.py` drift-protection suite.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `generate_security_report.py::main` (new emit-call) | `read_all_items` in `shared/scripts/triage.py` | JSONL (camelCase wire) |
| `performance_check.py::main` (new emit-call) | `read_all_items` | JSONL |
| `surface_verification.py::main` (new emit-calls × 3 conditions) | `read_all_items` | JSONL |
| `check_drift.py::main` (new emit-call) | `read_all_items` | JSONL |
| `artifact_sync.py::detect_drift` (new emit-call) | `read_all_items` | JSONL |

No new on-disk format is introduced; the JSONL schema and storage API
are unchanged. The 8-category boundary-probe matrix from
`references/boundary-probes.md` is satisfied by the existing
`test_triage_storage.py` suite — these per-producer tests focus on
correct call-shape, not on storage-format edge cases.

## Confidence Calibration

- **Boundaries touched:** Triage JSONL (`.shipwright/triage.jsonl`,
  write-only from each of 5 producer call sites). Read side is exercised
  by tests via `read_all_items`. The 8-category boundary checklist is
  satisfied by the existing iterate-1a `test_triage_storage.py` for the
  storage layer; this iterate adds round-trip tests at the
  producer→storage→reader layer.
- **Empirical probes run:**
  1. **Producer→file→reader round-trip** for each of the 5 new emit
     helpers (40 tests across 4 files, all PASS). Each test calls the
     helper with synthetic findings, then reads back via
     `read_all_items` and asserts on the resolved schema (source,
     severity, kind, dedupKey, suggestedPriority, suggestedDomain).
     Finding: schema lines up across all producers; no field-name
     mismatches.
  2. **`match_commit=True` semantics for F0.5**: distinct `run_id` must
     create distinct items (`test_different_run_id_creates_distinct_item`:
     PASS); distinct `surface` for same `run_id` must also create
     distinct items (`test_different_surface_creates_distinct_item`:
     PASS). Finding: dedup-key structure is collision-free across all
     three condition values.
  3. **`match_commit=False, window=None` semantics for drift**: second
     invocation with identical input produces zero new items
     (`test_check_drift_dedups_across_sessions`: PASS,
     `test_artifact_sync_dedups_across_sessions`: PASS). Finding:
     drift findings stay as single triage entries indefinitely until
     resolved, matching the compliance pattern.
  4. **F0.5 `EXIT_INVALID_ARGS` exclusion**: visual inspection +
     `_EXIT_TO_CONDITION` map literally omits exit code 1. Tests do
     not call the helper with `EXIT_INVALID_ARGS` (it's a config error,
     not a substantive fail-closed). Finding: config-error exits do
     NOT pollute the triage inbox.
  5. **Two drift producers emit compatible items**:
     `test_both_sites_emit_compatible_items` reads items from both
     `check_drift` and `artifact_sync` emissions through the same
     `read_all_items` consumer. Finding: schema is identical across
     producer sites.
  6. **Top-level wrappers never re-raise**: all 5 call-site wrappers in
     `main()` / `detect_drift()` wrap the emit-helper call in
     try/except + stderr log. Visual inspection confirmed. The
     iterate-1a `_emit_tier1_fails_to_triage` precedent has the same
     contract.
- **Edge cases NOT probed + why acceptable:**
  - Operator-input edge categories (POSIX `export`, inline `# comment`,
    quoted `#`): N/A — triage JSONL is machine-only, gitignored,
    append-only, never hand-edited.
  - Concurrent producers racing the same dedup key: covered by
    iterate-1a's `test_idempotent_concurrency_under_lock` against the
    underlying `append_triage_item_idempotent`. Not re-tested at the
    producer wrapper layer.
  - Heavy module imports (Playwright, subprocess, urllib) triggered by
    test loading: verified by inspection that the new emit-helpers
    are side-effect-free at module import time. Tests exercise the
    helpers without invoking `main()`, so heavy dependencies never
    run during test collection.
- **Confidence-pattern check:** no "are you confident" question has
  received a "yes" + subsequent finding in this session. Asymptote
  heuristic: marginal probe (Probe 6) returned no finding; all 8
  applicable categories covered; stopping rule met.

## Verification (medium+)

- **Surface:** cli
- **Runner command:**
  `bash -c "cd shared && uv run pytest tests/test_security_triage_emit.py tests/test_performance_triage_emit.py tests/test_f0_5_triage_emit.py tests/test_drift_triage_emit.py -v"`
- **Evidence path:** stdout captured into
  `.shipwright/runs/iterate-2026-05-14-triage-producers-2/surface_verification.log`
- **Justification:** n/a (surface=cli runs the empirical producer
  round-trips, exactly the user-erlebbare behaviour change in this
  iterate)
