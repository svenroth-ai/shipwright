# Iterate: Design verifier must skip projects that never ran the design phase

- **Run ID:** `iterate-2026-07-23-design-verifier-skip-no-design-phase`
- **Intent:** BUG (kind: bug-fix)
- **Complexity:** medium
- **Spec Impact:** MODIFY (a compliance gate's pass/skip/fail semantics change)
- **Source:** triage `trg-d26da6f4` (shipwright-webui compliance audit, P2, engineering)

## Problem (root cause)

`check_design_fr_coverage` (`shared/scripts/tools/verifiers/design_checks.py`),
surfaced by the compliance detective audit as **C1**
(`plugins/shipwright-compliance/scripts/audit/group_c.py` →
`_CHECK_TO_ID` maps it to `"C1"`), returns a HIGH failure when
`.shipwright/designs/design-manifest.md` is absent **but planning FRs exist**.

That manifest is produced only by `/shipwright-design` (the design phase).
An **adopted** (brownfield) project never runs that phase:
`plugins/shipwright-adopt/scripts/lib/config_writer.py` defaults
`completed_steps = ["project", "plan", "build", "test"]` (no `"design"`) and
seeds `phase_history` only from those steps. shipwright-webui is exactly this
shape — FR table present, only `visual-guidelines.md` under `.shipwright/designs/`,
no manifest. So C1 demands an artifact from a phase that by construction never ran.

The check already has the correct *shape* of escape hatch for a sibling case —
`_is_no_ui_scope()` skips when `scope=library`. It lacks the equivalent for
"the design phase was never part of this project's lifecycle".

Why it stayed hidden: for months the check returned "no planning FRs — coverage
trivially satisfied" on a **wrong basis** — the older spec parser did not
recognise the adopted FR-table shape, so `collect_requirements_from_planning`
returned empty. A parser upgrade then began returning the FRs (32 → 42 across
historical specs) and flipped C1 to HIGH-fail with **no change to the project**.

## The signal, and the timing trap

Fix per triage: skip when the design phase is absent from `completed_steps`.

**Trap:** `plugins/shipwright-run/.../step_planning.py` runs `validate_phase`
(→ `_validate_design` → `run_design_checks`, which runs both phase-own checks)
**before** it appends `"design"` to `completed_steps`. So during a *real*
greenfield design phase, `"design"` is not yet in `completed_steps`. A naïve
**top-level** guard would therefore skip the FR-orphan / screen-existence
enforcement exactly when it is supposed to run → regression.

**Resolution:** gate only the **`if not manifest.exists()` branch**. When a real
design phase ran, the manifest exists, the guard is never reached, and all
enforcement runs unchanged (`_validate_design` also only reaches the canon
checks when mockups exist for every split). The skip fires only for the precise
buggy state: FRs present **and** manifest genuinely absent **and** design never
a completed step.

## Fix

`shared/scripts/tools/verifiers/design_checks.py`:

1. Add `_design_phase_ran(project_root) -> bool` (mirrors `_is_no_ui_scope`):
   `True` iff `"design"` is in `completed_steps` of `shipwright_run_config.json`.
   **Fail-loud:** missing / unreadable / malformed / undecodable config,
   non-dict, or a non-list `completed_steps` all return `True` (run the check,
   fail loud) — a broken config must never buy a silent free pass.
2. `check_design_fr_coverage` (detective-audit C1) only: in the
   `if not manifest.exists()` branch, return SKIP when `not _design_phase_ran()`,
   else keep the existing FAIL.
3. `check_design_manifest_screens_exist` is **deliberately left unguarded**
   (Option B, code-review N1): it is NOT part of the detective audit and never
   runs on an adopted project (the between-phase validator reaches it only once
   mockups exist), so it stays the strict manifest-presence sentinel. Guarding
   it would mask a design phase that wrote mockups but no manifest — and by
   staying strict it *mitigates* that same window for the FR-coverage check.
4. Harden both config-reader helpers (`_is_no_ui_scope`, `_design_phase_ran`)
   to `encoding="utf-8-sig"` + catch `UnicodeDecodeError` (WP8/F24 convention).
   A BOM'd `scope=library` config was itself a latent false-C1 trigger.
5. Comment near `_NO_UI_SCOPES` names the orthogonal design-phase skip.
6. `shipwright_bloat_baseline.json`: grandfather `design_checks.py` (342) and
   `test_verifiers_design.py` (450) at exact newline count — both cross 300 as
   long-but-coherent modules; matches every already-baselined sibling verifier
   / test (avoids a self-inflicted Group-H H1 finding).

## Acceptance Criteria

- **AC1** — Adopted project (scope≠library, `completed_steps` has no `"design"`,
  planning FRs present, no `design-manifest.md`): `check_design_fr_coverage`
  returns SKIP (`ok is None`, `is_skipped`), not FAIL.
- **AC2** — Real drift (`"design"` ∈ `completed_steps`, FRs present, manifest
  absent): `check_design_fr_coverage` still FAILs.
- **AC3** — Phase-validator flow preserved: manifest **present** with an orphan
  FR while `completed_steps` lacks `"design"` (mid-design-validation) → still
  FAILs on the orphan (proves the guard is manifest-gated, not top-level).
- **AC4** — `check_design_manifest_screens_exist` unchanged: still FAILs on a
  missing manifest (its correct behaviour; never runs on an adopted project).
- **AC5** — All existing `test_verifiers_design.py`, compliance Group-C, and
  scope=library behaviours unchanged.
- **AC6** — Config-reader robustness: a BOM'd `run_config` is parsed (BOM'd
  `scope=library` still SKIPs; BOM'd no-design still SKIPs); undecodable bytes
  fail loud (no crash) → FAIL.

## Confidence Calibration

- **Boundaries touched:** reads `shipwright_run_config.json` (`scope`,
  `completed_steps`) — same read boundary as the existing `_is_no_ui_scope`; no
  new serialization surface (read-only, existing artifact). Consumer of the
  result: the compliance detective audit (`group_c.py` C1) and the between-phase
  validator (`phase_validators._validate_design`).
- **Empirical probes run:**
  - Traced the timing trap live: `step_planning.py:152-190` runs `validate_phase`
    (→ `run_design_checks`) BEFORE appending `"design"` to `completed_steps` →
    confirmed a top-level guard would regress the validator; manifest-gated
    placement avoids it (probe = AC3 test, green).
  - Confirmed detective audit wires only `check_design_fr_coverage` as C1
    (`group_c.py:29`, `audit_adapters.py:328`) → sister check needs no guard.
  - External review (GPT+Gemini via OpenRouter): surfaced the missing
    `UnicodeDecodeError` / BOM gap → fixed + pinned by AC6 tests.
- **Test Completeness Ledger:** see `shipwright_test_results.json`
  `iterate_latest.test_completeness` (every behaviour → tested; 0 untested).
- **Confidence-pattern check:** depth — fail-loud enumerated over all 6
  broken-state paths; breadth — skip / drift-FAIL / regression-guard / library /
  BOM / undecodable all covered. No `cross_component` machinery touched (a
  verifier module, not `verify_phase`/hooks/merge-resolver), so no integration
  behaviour required.
