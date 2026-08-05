# Iterate Spec: F5b dashboard regen tolerates WebUI's string-shaped test-status layers

- **Run ID:** iterate-2026-08-05-f5b-dashboard-webui-unit-shape
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal
`update_build_dashboard.py::_test_status_from_iterate` crashes with
`AttributeError: 'str' object has no attribute 'get'` whenever
`shipwright_test_results.json.iterate_latest`'s `unit` (or a sibling layer
key) is a pre-rendered human-readable string instead of the documented
`{status, passed, total}` mapping (F5.md). WebUI's historical F5 evidence
producer writes that string shape, so F5b's dashboard regeneration fails on
WebUI iterates. Moved from shipwright-webui `trg-cb7d4938` (triage
`trg-3e49151c`). Make the renderer accept both documented shapes without
weakening the existing structured-mapping handling. Not touching the WebUI
producer itself — this card is the consumer-side fix only.

## Acceptance Criteria
- [x] `_test_status_from_iterate` (and its helpers) render a layer given as
      a non-empty string (`"{Label}: {string}"`, internal whitespace/
      newlines collapsed to a single space so the row stays one markdown
      line, and `\`/`|` Markdown-escaped via the shared `escape_cell`
      helper) instead of raising `AttributeError`, for
      `unit`/`integration`/`pgtap`/`e2e` (all of which carry a `total`) and
      for `smoke` (status-only, no `total`).
- [x] The existing structured-mapping path (`{status, passed, total}`)
      renders byte-identical output to before this change — verified by the
      pre-existing tests in `TestEventTestStatus` continuing to pass
      unmodified.
- [x] A blank/whitespace-only string layer renders no line for that layer
      (parity with the pre-existing "total == 0 → omit" behavior for the
      mapping shape).
- [x] A layer key absent entirely from `iterate_latest` (not even an empty
      dict), or explicitly `null`, renders no line and does not crash.
- [x] `uv run shared/scripts/tools/update_build_dashboard.py --project-root
      <dir> --session-id <sid> --run-id <run>` exits 0 and produces a
      correctly rendered `## Test Status` section against a
      `shipwright_test_results.json` fixture whose layers use the WebUI
      string shape (verified manually end-to-end during F-debug Phase 2;
      pinned by the new pytest cases as the durable regression guard).

## Spec Impact
- **Classification:** none
- **NONE justification:** this fixes a crash in build-dashboard rendering,
  an internal Shipwright tooling artifact with no FR row in
  `.shipwright/planning/01-adopted/spec.md` — it restores tolerant
  behavior the F5.md contract never explicitly ruled out for a second
  producer, it does not change any spec'd product capability.

## Out of Scope
- The WebUI historical F5 evidence producer itself (explicitly excluded by
  the card — "Do not change the WebUI historical producer in this card").
  That repo is out of this monorepo's tree.
- Defining/documenting the exact WebUI string format. No such format is
  written down anywhere reachable from this repo (confirmed by search); the
  fix treats the string as opaque, already-formatted display text rather
  than parsing it, so it is correct for any string content.
- Any other consumer of `iterate_latest` (e.g. compliance test-evidence
  collectors) — none of those were found to read the same `unit`/etc. keys
  with the same `.get()` assumption; out of scope unless a follow-up finds
  otherwise.

## Design Notes
n/a — no UI/design surface; this is a Markdown-rendering tooling fix.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| WebUI's historical F5 evidence step (external repo, unchanged) + this monorepo's own F5 (`stamp_test_results.py` et al., per F5.md) | `update_build_dashboard.py::_test_status_from_iterate` (this change) | JSON (`shipwright_test_results.json.iterate_latest.{unit,integration,pgtap,e2e,smoke}`) |

`touches_io_boundary` was checked via the Stage-2 diff-driven detectors
(`risk_detectors.is_io_boundary_change`) against the planned file list and
did **not** fire — the change only reads an already-parsed dict via
`.get()`, it does not add a new `json.load`/`yaml.safe_load` call or touch
an `.env*`/`hooks.json`/`*_config.json`/`*_state.json` path. Confidence
Calibration is still populated below because complexity is medium.

## Confidence Calibration
- **Boundaries touched:** `shipwright_test_results.json.iterate_latest.{unit,integration,pgtap,e2e,smoke}`
  read path only (see Affected Boundaries above).
- **Empirical probes run:**
  1. Reproduced the crash directly (pre-fix) with a WebUI-shaped fixture
     (`unit: "833 passed, 0 failed"`) — confirmed `AttributeError` at
     `update_build_dashboard.py:287`, matching the reported symptom exactly.
  2. Ran `git blame` on the crash site — confirmed not a regression; the
     dict-only assumption is original code from 2026-04-06/09, predating
     WebUI's independent historical-evidence producer (Phase 3 of F-debug).
  3. Post-fix, ran the same crash-reproducing fixture through both the
     direct function call and the full `update_build_dashboard.py` CLI
     entrypoint end-to-end against a scratch project directory — exit 0,
     `## Test Status` rendered `Unit: 833 passed, 0 failed | Integration: 12
     passed | E2E: 5/5 | Smoke: pass | (iterate)` correctly for a
     string+mapping mixed fixture.
  4. Ran the full existing `TestEventTestStatus` class (6 pre-existing
     cases) post-fix — all pass unmodified, confirming the mapping path is
     byte-identical to before.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Each total-bearing layer (`unit`/`integration`/`pgtap`/`e2e`) as a non-empty string renders `"{Label}: {string}"` instead of crashing | tested | `test_build_dashboard.py::TestEventTestStatus::test_status_from_iterate_webui_string_shape_all_total_bearing_layers PASSED` |
  | 2 | `smoke` as a non-empty string renders `"Smoke: {string}"` instead of crashing, alongside missing total-bearing keys staying silently omitted | tested | `test_build_dashboard.py::TestEventTestStatus::test_status_from_iterate_webui_smoke_string_shape PASSED` |
  | 3 | A string layer with embedded newlines/repeated whitespace collapses to one markdown line | tested | `test_build_dashboard.py::TestEventTestStatus::test_status_from_iterate_string_layer_collapses_internal_whitespace PASSED` |
  | 4 | A mapping-shaped layer (e.g. `unit`) renders identically to before when a sibling key (e.g. `integration`) uses the string shape | tested | `test_build_dashboard.py::TestEventTestStatus::test_status_from_iterate_mixed_string_and_mapping_shapes PASSED` |
  | 5 | A blank/whitespace-only string layer renders no line, parity with `total==0` mapping behavior | tested | `test_build_dashboard.py::TestEventTestStatus::test_status_from_iterate_blank_string_layer_omitted PASSED` |
  | 6 | Pre-existing mapping-shape behavior (dict `{status,passed,total}`) unaffected by this change | tested | full pre-existing `TestEventTestStatus` suite (6 cases) PASSED unmodified |
  | 7 | CLI regeneration (`update_build_dashboard.py` entrypoint, the actual F5b call site) completes against a WebUI-shaped fixture | tested | manual CLI run in F-debug Phase 2/5, exit 0, correct `## Test Status` output (see probe 3 above); durably pinned by behaviors 1-4 exercising the same `generate_dashboard()` path the CLI entrypoint calls |
  | 8 | A `\|` inside a string-shaped layer is Markdown-escaped (`\\\|`), not left raw — the same WebUI-originated pipe-character row-shift failure mode `escape_cell` was built for (`markdown_table.py` docstring) | tested | `test_build_dashboard.py::TestEventTestStatus::test_status_from_iterate_string_layer_escapes_pipe PASSED` |
  | 9 | An explicit JSON `null` for a layer (neither dict nor string) renders no line and does not crash, same as an absent key | tested | `test_build_dashboard.py::TestEventTestStatus::test_status_from_iterate_null_layer_omitted PASSED` |
  | 10 | A `\` inside a string-shaped layer is Markdown-escaped (`\\`), independently of the `\|` case (`escape_cell` escapes backslash first so a later `\|` substitution cannot collide with one) | tested | `test_build_dashboard.py::TestEventTestStatus::test_status_from_iterate_string_layer_escapes_backslash PASSED` |

  Counts: testable 10, tested 10, untestable 0, untested_testable 0.
- **Confidence-pattern check:** Asymptote (depth) — external review ran
  three times across the plan and code-review gates (two plan rounds,
  Branch A, deepseek=approve/openai=revise both times; one code-review
  round, Branch A, openai=approve/deepseek=revise), no high-severity or
  contradictory findings at any point, and each round surfaced real,
  non-duplicate gaps: round 1 → missing per-layer string coverage +
  embedded-newline handling; round 2 → pipe-character escaping (a
  documented WebUI-originated failure class this repo already has a
  purpose-built helper for, `escape_cell`) + an explicit-`null` edge case;
  round 3 (code-review cascade, post-commit-prep) → backslash-escaping
  coverage, the other half of the same `escape_cell` transform pipe-escaping
  already exercised. All five gaps were closed with new probes and ledger
  rows before F0 — the "yes, then a finding" pattern this check exists to
  catch, repeated three times with diminishing findings each round (each
  round found a narrower, more marginal gap than the last), which is the
  expected shape of convergence rather than an open-ended loop. Coverage
  (breadth) — every ledger row is `tested`, 0 `untested_testable`.
  `cross_component` risk flag was checked against the diff-driven detector
  and did not fire (single-module rendering fix, not FRAMEWORK
  cross-component machinery), so no `category:"integration"` behavior is
  owed.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run pytest shared/scripts/tests/test_build_dashboard.py::TestEventTestStatus -v`
- **Evidence path:** `.shipwright/runs/iterate-2026-08-05-f5b-dashboard-webui-unit-shape/surface_verification.json`
