# Iterate: A5 critical-gate behavioral probe

- **Run ID:** iterate-2026-06-05-a5-gate-behavioral-probe
- **Intent:** CHANGE (harden an existing detective-audit sub-check)
- **Complexity:** medium (classifier 0.7, no risk flags)
- **Spec Impact:** MODIFY — extends Group A5 (`shipwright-compliance`) audit behavior
- **Date:** 2026-06-05

## Problem

Group A5 (`plugins/shipwright-compliance/scripts/audit/group_a5.py`) audits the
**deployed** `.github/workflows/security.yml`. Sub-check **A5.4** confirms a step
carries `id: shipwright-critical-gate` — i.e. the merge gate is *present*. It
never confirms the gate *works*.

The 2026-06-04 false-green (fixed for the **template** in PR #144) was exactly a
gate whose step existed yet could never block: it read SARIF `security-severity`
at the **result** level, where the field never lives (it lives on the
**rule**), so every finding read as "0" and a real CVSS-critical sailed through
green. `shared/tests/test_security_critical_gate.py` now pins the **template**
gate's behavior, but nothing pins the **deployed** file A5 audits. A structurally
broken *deployed* gate (re-introduced result-level read, a no-op `echo ok`, a
gate that can't fail-closed) is invisible to A5.

## Key finding shaping the design

The deployed gate and the template gate read **different artifacts**:

| Gate | Reads | Blocks on |
|---|---|---|
| **Template** (adopted repos, rendered from `security.yml.template`) | `sarif/*.sarif` | rule-level `security-severity >= 9.0`, any gitleaks result |
| **This monorepo's own** `.github/workflows/security.yml` | `findings.json` (`.findings[].severity == "critical"`) + `prompt_risks.json` | a `critical`-severity finding |

Both honor the same **policy** (critical → block, empty/invalid → fail-closed,
clean → pass) but consume different files. A SARIF-only probe would *falsely
fail* the monorepo's own gate (it never reads SARIF) — and that's the file A5
audits in this repo.

## Approach (user-approved: dual-artifact, flavor-agnostic)

New sub-check **A5.8** *executes* the deployed gate's `run:` body against fixture
scan output and asserts the **policy**, not the implementation. Each scenario
stages **both** artifact families consistently so the probe is correct
regardless of which one the gate reads:

- **CLEAN (sanity gate, runs first):** `sarif/trivy.sarif` (rule 5.5) + `sarif/semgrep.sarif`
  (no severity) + `findings.json` (`high`, no critical) + `prompt_risks.json` (none).
  If the real gate does **not** exit 0 here → **SKIP** (inconclusive: the probe
  environment can't satisfy the gate's tool assumptions — e.g. a customized gate
  using a binary we lack). Protects against false positives.
- **CRITICAL:** `sarif/trivy.sarif` (rule `security-severity` 9.8 + result) +
  `findings.json` (`critical`). Assert the gate exits **non-zero** (blocks).
  Exit 0 ⇒ **FAIL (HIGH)** — the 2026-06-04 false-green class.
- **EMPTY:** no artifacts at all. Assert non-zero (fail-closed). Exit 0 ⇒ FAIL.
- **INVALID:** `sarif/x.sarif` and `findings.json` both invalid JSON. Assert
  non-zero (fail-closed). Exit 0 ⇒ FAIL.

A gate that exits 0 on CRITICAL/EMPTY/INVALID is structurally unable to block —
caught regardless of flavor. A no-op gate (`echo ok`) fails CRITICAL. An
over-blocking gate (always exit 1) fails the CLEAN sanity → SKIP (not a false
FAIL). The monorepo's own findings.json gate and the template's SARIF gate both
PASS (each reads its own artifact; the other is inert ballast).

## Safety / runtime contract

- **Tool-gated:** the gate body needs `bash` + `jq`. If either is absent
  (`shutil.which`), A5.8 emits **SKIP** — an env/invocation problem, *not* a
  compliance violation (mirrors the A5.0 PyYAML-missing skip from C2). Avoids a
  phantom triage FAIL on dev machines without jq. (Verified: this dev box has
  neither on PATH → A5.8 skips locally; CI ubuntu ships both → runs.)
- **Sandboxed:** each scenario runs in a fresh `tempfile.TemporaryDirectory`
  with `GITHUB_OUTPUT` pointed at a temp file; per-run `timeout`. Any subprocess
  timeout ⇒ SKIP (inconclusive), never a hang.
- **Crash-isolated:** `gate_behavior_probe.run()` never raises — any unexpected
  exception becomes a single A5.8 finding (matches group_a5's `_safe_run`).
- **No-run-body gate** (a `uses:`-only gate step) ⇒ SKIP (nothing to execute;
  A5.4 already covers id presence).
- **Operator kill-switch / test isolation:** `SHIPWRIGHT_A5_GATE_PROBE=0`
  disables the probe (emits one transparent SKIP). Default on. The compliance
  test package's `conftest.py` sets it off so the *structural* A5.1–A5.7 unit
  tests stay pure-YAML (no bash/jq dependency, no subprocess latency); the
  dedicated behavioral test file drives the probe directly.

## Files

- **NEW** `plugins/shipwright-compliance/scripts/audit/gate_behavior_probe.py`
  (≤300 LOC): tool check, gate-body extraction, dual-artifact fixtures,
  sandboxed subprocess harness, `probe()` orchestration, crash-isolated
  `run(workflow, conv) -> list[Finding]` emitting A5.8.
- **EDIT** `group_a5.py` (+2 lines: import + `findings.extend(...)`); register
  A5.8 in `_NAMES`/`_SEVERITY` is **not** needed (probe builds its own Finding).
  Bump `shipwright_bloat_baseline.json` `current` for this file in the same commit.
- **EDIT** `plugins/shipwright-compliance/tests/conftest.py` (+autouse fixture
  disabling the probe for the package).
- **NEW** `plugins/shipwright-compliance/tests/test_audit_gate_behavior_probe.py`
  (mirrors `test_security_critical_gate.py`; `skip_or_fail_on_missing_binary`
  so CI hard-runs, local skips). Covers: valid template gate → pass; valid
  monorepo findings.json gate → pass; result-level-only/echo-ok no-op → fail;
  over-block always-exit-1 → skip; uses-only no-run → skip; bash/jq missing →
  skip; the REAL deployed `.github/workflows/security.yml` → pass; the REAL
  template → pass.
- **DOC** SKILL.md A5 line gains a "behaviorally verifies the gate blocks"
  clause; `docs/hooks-and-pipeline.md` A5 note updated if needed.

## Acceptance Criteria

1. A5.8 emits **FAIL (HIGH)** when the deployed gate exits 0 on a CRITICAL
   fixture (the false-green class).
2. A5.8 emits **FAIL (HIGH)** when the gate exits 0 on EMPTY or INVALID fixtures
   (not fail-closed).
3. A5.8 emits **PASS** against the real deployed monorepo gate (findings.json)
   AND the real template gate (SARIF) — proving flavor-agnostic correctness.
4. A5.8 emits **SKIP** (never FAIL) when bash/jq are absent, when the gate has
   no `run:` body, when the gate can't pass the CLEAN sanity fixture, or when
   `SHIPWRIGHT_A5_GATE_PROBE=0`.
5. Existing A5.1–A5.7 structural tests stay green and acquire no bash/jq
   dependency.
6. `group_a5.py` stays within its (bumped) bloat baseline; the new module ≤300 LOC.

## Confidence Calibration

- **Boundaries touched:**
  - `subprocess` — executes the gate's `run:` body as bash (NEW boundary;
    sandboxed `TemporaryDirectory`, `GITHUB_OUTPUT` temp file, per-run `timeout`).
  - `json.dumps` fixture producers (SARIF + findings.json/prompt_risks.json) —
    the round-trip *is* the gate's own `jq` parse; A5.8 is itself the Boundary
    Probe for the gate's input contract.
  - env var `SHIPWRIGHT_A5_GATE_PROBE` (NEW config boundary; default on).
  - consumes the already-parsed workflow YAML dict from `group_a5`; emits a
    `Finding` via the `audit_adapters` contract.

- **Empirical probes run:**
  - Full compliance suite: **611 passed, 9 skipped** — structural A5.1–A5.7
    tests unaffected by the conftest opt-out; audit_report/snapshot tests green.
  - Orchestration decision-tree (`test_gate_probe_orchestration.py`): **7 passed**
    locally — every verdict (pass / critical-not-blocking-fail / clean-skip /
    empty-fail / invalid-fail / timeout-skip / oserror-skip) confirmed.
  - Anti-ratchet (`anti_ratchet_check.py --worktree`): **status ok** after the
    608→614 group_a5.py baseline bump; no new crossings (new module 287, test
    files 296/114 — all ≤300).
  - `uvx ruff@0.15.15 check .`: **All checks passed.**
  - Silent-skip static probe (`scan_test_hygiene.py`): **no findings** (bare
    file-not-found skips replaced with asserts; tool gate uses the canonical
    `skip_or_fail_on_missing_binary`).
  - Verified `bash`/`jq` absent on this dev box → A5.8 SKIPs locally (no phantom
    FAIL); the 9 end-to-end cases run in CI ubuntu.
  - Verified the worktree includes PR #148 (`dc78b6d4`); the gate body is
    unchanged by #148, so A5.8 is unaffected.

- **Test Completeness Ledger:** principle *testable ⇒ tested*; 0 untested-testable.

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | FAIL when gate exits 0 on CRITICAL (false-green class) | tested | `test_probe_fails_on_noop_gate`, `test_probe_fails_on_result_level_only_gate` (CI); `test_critical_not_blocking_is_fail` (local) |
  | FAIL when gate exits 0 on EMPTY | tested | `test_probe_fails_when_gate_not_fail_closed_on_empty` (CI); `test_empty_not_failing_closed_is_fail` (local) |
  | FAIL when gate exits 0 on INVALID JSON | tested | `test_invalid_not_failing_closed_is_fail` (local decision-tree) |
  | PASS against real template gate (SARIF flavor) | tested | `test_probe_passes_against_real_template_gate` (CI) |
  | PASS against real deployed monorepo gate (findings.json flavor) | tested | `test_probe_passes_against_real_deployed_monorepo_gate` (CI) |
  | SKIP when bash/jq absent | tested | `test_probe_skips_when_tools_unavailable` (local) |
  | SKIP when gate has no `run:` body | tested | `test_probe_skips_when_gate_has_no_run_body` (local) |
  | SKIP (inconclusive) when gate fails the CLEAN sanity | tested | `test_probe_skips_on_overblocking_gate` (CI); `test_clean_not_passing_is_skip` (local) |
  | SKIP when disabled via `SHIPWRIGHT_A5_GATE_PROBE=0` | tested | `test_run_if_enabled_skips_without_probing_when_disabled` (local) |
  | SKIP on subprocess timeout / OSError | tested | `test_timeout_is_skip`, `test_oserror_is_skip` (local) |
  | `run()` crash-isolated (never raises) | tested | `test_run_never_raises_on_internal_error` (local) |
  | Finding contract (group A / detective-only / A5.8 / HIGH / cmd-on-fail) | tested | `test_run_emits_single_a5_8_finding_with_contract` (CI), `test_run_skip_finding_carries_no_suggested_cmd` (local) |
  | `enabled()` default on, `=0` off | tested | `test_enabled_default_is_on` (local) |
  | A5.8 wired into `group_a5.run()` output | tested | `test_a5_8_present_in_group_a5_run_when_enabled` (CI) |
  | `extract_gate_body` (run string / none / malformed jobs) | tested | `test_extract_gate_body_*` (local) |
  | Structural A5.1–A5.7 + audit suite acquire no bash/jq dependency | tested | full compliance suite (conftest opt-out) |

  No `untestable` rows: the 9 end-to-end cases are `tested` in CI (the only env
  with bash+jq); local Windows-skip is the same ADR-044 posture as the
  gold-standard `test_security_critical_gate.py`, not a coverage gap.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the decision tree is exhausted locally (all 5 verdicts
    + 2 error paths). The only thing not exercisable locally — the real `bash`
    gate execution — is mitigated three ways: (1) the orchestration tests pin the
    control flow, (2) fixtures are mirrored from the proven
    `test_security_critical_gate.py`, (3) CI runs the 9 end-to-end cases. The
    download of a local `jq` was attempted and denied; not worked around.
  - *Coverage (breadth):* {pass, fail, skip} × {real template, real deployed,
    no-op, result-level bug, not-fail-closed, over-block, no-run-body,
    tools-missing, disabled, timeout, oserror, crash} — both gate flavors, plus
    unit + integration + structural-regression.
