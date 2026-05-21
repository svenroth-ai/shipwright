# Iterate Spec: B.3 — test-evidence Layer column + per-layer FAIL triage

- **Run ID:** iterate-2026-05-21-b3-test-evidence-layer-and-triage
- **Type:** feature
- **Complexity:** small
- **Status:** draft

## Goal

Close the artifact-polish plan's Iterate B.3 by realizing ADR-054 D2 +
D3 on the producer side, plus the corresponding schema extension:

1. **Test Progression Layer column** — per-row `unit | e2e | mixed | —`
   classification derived from `WorkEvent.tests`.
2. **Full Suite Runs table breakout** — Integration + pgTAP columns
   alongside Unit / E2E, sourced from the new layers-dict keys.
3. **`record_event` schema extension** — `--integration-passed/total`
   and `--pgtap-passed/total` CLI flags wire into `test_run` events'
   `layers.integration` and `layers.pgtap` keys.
4. **Per-layer FAIL triage producer** — `emit_test_failure_triage`
   emits one `source="test-evidence"` item per failing layer with the
   originating test_run's `event_id` (dogfoods ADR-054 D5).

## Acceptance Criteria

- [ ] **AC-1** `record_event.py` accepts `--integration-passed`,
  `--integration-total`, `--pgtap-passed`, `--pgtap-total`. When at
  least one is set, the emitted `test_run` event carries a
  `layers.integration` (or `layers.pgtap`) sub-dict with the supplied
  counts.

- [ ] **AC-2** A `test_run` event built without any layer flags omits
  the `layers` key entirely (no empty-dict noise on the wire).

- [ ] **AC-3** `TestRunEvent.from_dict` reads the new keys when
  present and defaults `integration_passed/total` / `pgtap_passed/total`
  to `0` for legacy events.

- [ ] **AC-4** Test Evidence `## Full Suite Runs` table renders 8
  columns: `Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke
  | Date`. Layers with `total == 0` render as `—`.

- [ ] **AC-5** Test Evidence `## Test Progression` table gains a 4th
  column `Layer`. Classifier rules:
  - `tests.total > 0 AND tests.e2e_run = true` → `mixed`
  - `tests.e2e_run = true` only → `e2e`
  - `tests.total > 0` only → `unit`
  - otherwise → `—`

- [ ] **AC-6** `emit_test_failure_triage(project_root)` reads the
  latest `test_run` event and emits one triage item per layer where
  `passed < total`, using:
  - `source = "test-evidence"`
  - `dedup_key = "test-fail:<layer>"`
  - `severity`: `high` for e2e / integration / pgtap; `low` for unit
    (per ADR-054 D3)
  - `kind = "bug"`
  - `event_id = <latest test_run id>` (cross-link dogfood)
  - `launchPayload = "/shipwright-iterate --type bug"` + layer-scoped
    context block
  - `window_seconds = None`, `match_commit = False` (idempotent)

- [ ] **AC-7** For e2e failures, the detail body lists the top-10
  failing test IDs sourced from `data.test_results.e2e_failures`
  (shipwright_test_results.json) plus a `+N more` footer when >10.
  Other layers' detail line states the failing-count + a pointer to
  test-evidence.md.

- [ ] **AC-8** Re-running the producer against the same test_run state
  appends zero new items (idempotent dedup).

- [ ] **AC-9** When a previously-failing layer is green on the next
  test_run, the matching `source="test-evidence"` item flips to
  `dismissed` with `reason="testEvidenceResolved"` and
  `by="testEvidence"`.

- [ ] **AC-10** Operator-promoted items (`status=="promoted"`) are NOT
  auto-dismissed when the layer goes green (HIGH-2 contract from
  audit_detector).

- [ ] **AC-11** `update_compliance.py --phase iterate` (and any phase
  that regenerates `test-evidence.md`) invokes
  `emit_test_failure_triage` after the report is written. The result
  is echoed under `output["test_evidence_triage"]`. Per-emit errors
  surface via the `error` key, never aborting compliance updates.

## Out of scope

- **Per-test failure IDs for non-e2e layers** — `shipwright_test_results.json`
  carries `e2e.failures` but no analogous list for unit / integration
  / pgtap. The current SBOM-style "count + pointer" body is enough for
  solo dev; if a future iterate adds per-test failure lists for those
  layers, the emit producer reads them through the same
  `_failure_detail` boundary.

- **Suite-level granularity** — ADR-054 D2 explicitly rejected
  `(layer, suite)` granularity in favor of `(layer)`. Not relitigated.

- **Severity-vocabulary rename** — `info/warn/major/minor` rejected by
  ADR-054 D7. Stays critical/high/medium/low/info.

- **Per-work-event Integration / pgTAP layer classification** — the
  classifier only emits `unit | e2e | mixed | —` because the work_completed
  wire format doesn't carry granular layer info. Promoting that to
  per-work-event would require a `tests.layers` array on the
  work_completed wire — deferred.

## Review-driven additions (post external review)

- **Skipped-test false positive (Gemini-H1):** the FAIL-triage producer
  no longer treats `passed < total` as a guaranteed failure (skipped
  tests would have caused false-positive cards). Added an optional
  `failed` field on every layer (CLI: `--<layer>-failed N`); producer
  triggers on `failed > 0` when present, else falls back to the
  `total - passed` delta.
- **Negative / non-int CLI inputs (OpenAI-H3):** all
  `--<layer>-passed/total/failed` flags use a `_non_negative_int`
  argparse type that rejects negatives + non-integer strings at the
  CLI boundary.
- **`passed > total` / `failed > total` (OpenAI-H3 sibling):**
  `build_event` raises `ValueError` so corrupt payloads never reach
  the on-disk log.
- **Omitted layer ≠ green (OpenAI-M6):** `TestRunEvent` gains
  `*_evaluated` flags. The auto-dismiss sweep is scoped to layers
  the latest run *actually evaluated*; omitted layers don't flip
  prior cards.
- **Markdown injection / control chars (Gemini-L5 / OpenAI-M11):**
  `_sanitize` strips `\x00..\x1f` + `\x7f` from failure IDs; e2e
  failure IDs render inside backticks so residual metacharacters
  can't break the surrounding markdown.
- **Null-safe traversal (Gemini-L4):** `TestRunEvent.from_dict`
  uses `d.get("layers") or {}` so an explicitly-null `layers` field
  doesn't crash readers.

## Implementation Notes

- `record_event.py` extends the existing test_run branch with two new
  optional layer-pair blocks (integration, pgtap) right before the
  e2e block. Backward-compat tested in `shared/tests/test_record_event.py`.

- `TestRunEvent.from_dict` reads the new keys via the same
  `layers.get(name, {})` pattern. Default-zero fields keep legacy
  events readable.

- `_classify_work_event_layer` is a 5-line pure function — easy to
  unit-test and review.

- `emit_test_failure_triage` mirrors B.2's `emit_undeclared_triage`
  architecture: lazy-import triage API, idempotent append per layer,
  auto-dismiss by dedup-key delta, error accumulation in the returned
  dict.

- `update_compliance.py` now carries TWO triage producers (sbom +
  test-evidence). Both follow the same `try: emit; except: error`
  contract and surface telemetry in `output[<producer>_triage]`.

## Verification

- `uv run --extra dev pytest plugins/shipwright-compliance/tests/test_test_evidence.py
  -v` — 24 new tests (5 layer-classifier, 1 full-suite breakout, 11
  emit_triage incl. error-surface + dogfood, 2 backward-compat,
  +existing 5 = 31 total).

- `uv run --extra dev pytest shared/tests/test_record_event.py -v` —
  6 new tests on the `test_run` schema extension.

- Full compliance suite: 391 passed (baseline 372 + 19 new).

- Full shared suite: 2107 passed (baseline 2101 + 6 new).
