# Iterate Spec — P2.39: verify the F11 tree before push

**Run ID:** `iterate-2026-08-10-p2-39-f11-verify-local`
**Intent:** CHANGE
**Complexity:** medium (manually raised from the initial small estimate: this changes the delivery workflow that decides which commit CI judges).
**Spec impact:** NONE — no user-facing product behaviour changes.

## Problem

F0 invokes `scripts/verify_local.py` against the working tree before F6.  Tracked
finalization artifacts and F11's `ensure_current.py` integration can subsequently
change the commit that is pushed and judged by CI.  In particular, the integration
can bring in a changed workflow or CI-gate allowlist that F0 could not have read.

## Decision

Keep F0 as the cheap early pre-flight, and invoke the same guarded local gate again
in F11 immediately after `ensure_current.py` has completed and before any push.  A
non-zero late verdict stops delivery even though the run's work is already committed;
that late STOP is intentional and accepted by P2.39.

## Acceptance Criteria

- [x] **AC-1 — Verify every actual F11 pre-push tree.** F11 documents and executes a
  marker-guarded `scripts/verify_local.py` invocation after successful integration
  and regeneration, before the initial or delivery-refresh `git push`. A non-zero
  result STOPs F11; an absent or non-Shipwright script remains a no-op.
- [x] **AC-2 — Pin the ordering and failure contract.** Focused automated tests
  reject a missing second invocation, comment/prose-only text, an invocation before
  `ensure_current.py`, an invocation after either push, or a failure path that can
  fall through.
- [x] **AC-3 — Keep the workflow truthful.** The F11 reference, the SKILL summary,
  and hooks/pipeline documentation say that F0 is an early catch and F11 rechecks the
  regenerated pre-push tree. They state the accepted late STOP explicitly.

## Scope Boundary

P2.52's decision-drop scanning was investigated only to avoid reopening it: the
pre-commit hook is bloat-only, CI already invokes the prompt scanner, and origin/main
PR #615 added JSON decision-drop dispatch to close CI's prior blind spot. It is a
separate delivered card and is not modified here.

## Alternative considered

Moving the sole invocation from F0 to F11 would leave cheap, pre-commit feedback
behind the full suite and finalization work. Keeping both calls catches the common
case early and closes the integration tail at the only local point where the merged
result exists.

## Internal Plan Review

- **Ran:** yes
- **Verdict:** REVISE, then incorporated.
- **Findings:** The initial plan missed `pr_delivery_host.refresh_branch`, which can
  integrate and push during delivery after the initial F11 call. The implementation
  now rechecks the marked local gate before that refresh push, with red-path and
  ordering tests. The guide and mutation-resistant F11 wiring assertions were added.
- **Status:** 3 findings fixed; no scope outside P2.39.

## External Plan Review

- **Ran:** yes, via the authorized OpenRouter route.
- **Outcome:** neither configured reviewer returned a response because this runner has
  no `OPENROUTER_API_KEY`; the recorded evidence is an unavailable-provider result,
  not an invented approval.
- **Disposition:** the required local Sol/high review cascade remains the substantive
  review path for this run.

## External-Code-Review-Findings

| Finding | Disposition |
|---|---|
| Delivery refresh ran the local script without the documented project-root `uv run` context. | **accepted-and-fixed** — it now executes `uv run scripts/verify_local.py` with `cwd=project_root`; the runtime test asserts both argv and cwd. |
| A permission/read failure could be treated as a marker-absent no-op. | **accepted-and-fixed** — only a missing file or an undecodable non-marker candidate no-ops; other `OSError` values return a red verdict. |
| External diff did not show focused test files. | **rejected-with-reason** — the tests existed but were untracked, and `git diff HEAD` omits untracked files. They are now included through intent-to-add for the re-review and have passed locally. |
| Failure output was allegedly unavailable. | **rejected-with-reason** — the shared `_run` helper already captures stdout/stderr; the guard prints those captured streams when its marked gate is red. |
| Initial F11 marker inspection could skip on a `grep` read error. | **accepted-and-fixed** — only `grep` status 1 (marker absent) no-ops; every other inspection status now emits STOP and exits 1, pinned by a focused wiring assertion. |
| Delivery refresh treated every undecodable candidate as unmarked. | **accepted-and-fixed** — marker discovery now reads bytes, matching `grep`: undecodable unmarked consumers no-op, while an undecodable marked script executes the gate and can block push. |

## Test Completeness Ledger

| Behaviour | Disposition | Evidence |
|---|---|---|
| F11 runs the guarded local gate after integration and before push | tested | Focused F11 wiring tests |
| A local gate failure stops F11 | tested | Focused F11 wiring tests |
| F11 documentation accurately describes both checks and the accepted late STOP | tested | Focused F11 wiring tests |
