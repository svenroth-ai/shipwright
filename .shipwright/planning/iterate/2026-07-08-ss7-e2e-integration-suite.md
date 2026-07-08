# Iterate Spec — SS7: single-session E2E integration + cross-surface capstone

- **Run ID:** `iterate-2026-07-08-ss7-e2e-integration-suite`
- **Campaign:** `2026-07-07-single-session-pipeline` · sub-iterate **SS7** (capstone)
- **Intent:** FEATURE (capstone integration + regression test suite)
- **Complexity:** medium · **Spec Impact:** NONE (behavior-preserving — adds test
  files only; no product FR added/modified/removed). FR-gate: `change_type: tooling`.
- **Anchor:** `trg-9d973f4f` (campaign)

## Goal

Land the campaign's safety net: a monorepo E2E integration suite that plays a
single-session pipeline through all phases + build fan-out + **human-gate
pause/resume** + strict-stop, proves **cross-surface parity** (the loop is
surface-agnostic, so CLI ≡ WebUI by construction; chat honestly declines via the
S1a banner), proves an **in-flight multi-session run remains resumable**
(positive path + no single-session leak), and pins a **regression per known-bug
class** (section-writer persistence, external_review degraded-not-loud).

## Boundary — CLI half here, WebUI half = SS8

A true cross-surface E2E needs **both** CLI and WebUI (confirmed with Sven). The
WebUI Playwright flow lives in the separate `shipwright-webui` repo and depends
on the paired **S1b** track (Continue-fix + single-session board representation);
it cannot run green in this monorepo. This iterate delivers the **self-contained
CLI/monorepo half** and **registers SS8** (WebUI Playwright cross-surface E2E,
delivered in `shipwright-webui`, prereq S1b) in the campaign. AC2 is therefore
`deferred-to-SS8`, recorded in the decision-drop and `degraded[]`.

## Do NOT duplicate (already green — YAGNI)

| Concern | Owner |
|---|---|
| Full single-session pipeline + fan-out; strict-stop **at plan, no fan-out** (empty splits) | SS3 `test_single_session_pipeline.py` |
| Persistence guard (section-writer) — isolated | SS3 `TestPersistenceGuardCrossComponent`, unit `test_single_session_artifact_guard.py` |
| Kill-and-resume idempotent (single-session) | SS5 `test_single_session_resume_integration.py` |
| external_review degraded detection (subprocess, deep) | SS6 `shared/tests/test_external_review_degraded.py` |
| Human-gate pause/resume (unit + CLI) | SS5 `test_single_session_resume.py`, `test_single_session_cli.py` |
| Honest banner (chat surface) prose drift-guard | `test_run_skill_handoff_banner.py` |

## Net-new coverage (this iterate)

- **A — gate-walk capstone:** full single-session pipeline (all phases + build
  fan-out) walked **through** a `single-session-gate` pause→resume, asserting the
  observability event story (`dispatch`/`phase_result`/`human_gate_pause`/
  `human_gate_resume`) ends at `complete`. Section-writer regression is **threaded
  into** the plan phase of this walk (claim-unwritten → `artifacts_missing` → fix
  → continue) so the guard is proven mid-real-pipeline.
- **A' — strict-stop mid-fan-out:** a build failure DURING the serial split
  fan-out halts the run and plans NO successor split (split 02-ui never becomes a
  task; `strict_stop` emitted). Net-new vs SS3, whose strict-stop is at plan with
  empty splits (no fan-out) and asserts no events.
- **B — cross-surface parity:** the same pipeline driven under
  `CLAUDE_CODE_ENTRYPOINT=cli` vs `claude-vscode` produces an identical dispatch
  sequence + terminal state — the loop reads no surface/`SHIPWRIGHT_WEBUI` env, so
  CLI ≡ WebUI by construction. References the chat-banner drift-guard for the
  honest-decline half.
- **C — in-flight multi-session resumable:** crash a `multi_session` (default) run
  mid-flight → `recover-phase-task` → a fresh session **re-claims + completes** →
  pipeline advances, **and no `run_loop_*` files are created** (closes the
  positive-path hole; back-compat proof).
- **D — external_review roster pin:** a thin loud-fail contract regression
  (`finalize_review_output` degraded → exit 1) pointing to SS6 as deep owner —
  the campaign-level guarantee that the review gate can never silently no-op.

## Files

- `integration-tests/test_single_session_capstone.py` — A + B (new, <300 LOC)
- `integration-tests/test_cross_surface_backcompat.py` — C + D (new, <300 LOC)

## Confidence Calibration

- **Boundaries touched:** none in production code — this iterate ADDS test files
  only. Exercised surfaces (read-only, real subprocess): the orchestrator CLI
  (`single-session-next/-apply/-gate`, `claim/complete/recover-phase-task`),
  `run_loop_state.json`, `run_loop_events.jsonl`, `shared` `finalize_review_output`.
- **Empirical probes run:** 6/6 capstone tests green against the real subprocess
  CLI; full `integration-tests/` suite 184 passed / 2 deselected (no regression).
  External review (OpenRouter GPT + Gemini, success, not degraded) → 4 GPT
  findings, all fixed: parity helper now asserts the *correct* frontier per
  surface (not just cross-surface equality); external_review import no longer
  leaks `sys.path`; the chat-surface honest-decline reference is now *enforced*
  (banner drift-guard exists + SKILL.md chat branch declines), not just documented.
- **Test Completeness Ledger:** see below — every capstone behavior → `tested`
  with its scenario as evidence; 0 untested-testable.
- **Confidence-pattern check:** asymptote = each scenario drives the real CLI to a
  terminal/observable state (not a mock); breadth = single-session happy+gate+
  strict-stop, cross-surface parity, multi-session back-compat, review-gate roster;
  **integration composition** = both files are `category:"integration"` (the loop +
  lifecycle + observability + recovery compose across the subprocess boundary), the
  cross_component coverage the F11 verifier recomputes.

### Test Completeness Ledger (to finalize at F5)

| Behavior | Disposition | Evidence |
|---|---|---|
| Full single-session pipeline advances to `complete` through a human-gate pause/resume | tested | `test_single_session_capstone.py::TestFullPipelineThroughHumanGate` |
| Section-writer claim-unwritten rejected mid-pipeline, frontier intact, then completes | tested | same test (threaded into the plan phase of the walk) |
| Strict-stop mid-fan-out halts the run + plans no next split | tested | `…capstone.py::TestStrictStopMidFanout` |
| Loop dispatch sequence is the CORRECT pipeline AND identical across `CLAUDE_CODE_ENTRYPOINT` values | tested | `…capstone.py::TestCrossSurfaceParity` |
| Chat surface honestly declines (banner drift-guard exists + SKILL.md chat branch declines) | tested | `test_cross_surface_backcompat.py::TestChatSurfaceHonestDecline` |
| In-flight multi_session run recovers: crash → recover → re-claim → complete → advance | tested | `…backcompat.py::TestMultiSessionRemainsResumable` |
| multi_session recovery creates no `run_loop_*` single-session files | tested | same test (step 6) |
| external_review gate fails loud when degraded (roster pin) | tested | `…backcompat.py::TestExternalReviewGateCannotSilentlyNoop` |
| Green in CI | tested | F0 full run (184 integration + full unit suite) + CI |

## Out of scope

- WebUI Playwright browser flow (→ SS8, `shipwright-webui`).
- Refactoring SS3/SS5 shared CLI helpers (established per-file convention; not this iterate's concern).
- Any production-code change (unless a scenario surfaces a real bug — then handled per constitution).
