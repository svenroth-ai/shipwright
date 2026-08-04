# Iterate Spec: Retire obsolete runtime PID verifier

- **run_id:** `iterate-2026-08-04-runtime-process-identity`
- **status:** `implemented`
- **intent:** BUG
- **complexity:** medium
- **risk_flags:** `cross_component`
- **source:** P2.35 / `trg-70ad1a6b` (supersedes `trg-06641ec3`)

## Problem

`shared/scripts/tools/verifiers/runtime_checks.py` still reconciles task events
against `.shipwright-webui/pids.json`. The only producer was the WebUI process
governor. That governor was extracted with the WebUI and later deleted during
the external-launch pivot, so the repository retains a consumer and public
`verify_phase.py --phase runtime` surface for a format no active component
produces. Binding numeric PID liveness to a new identity would create an
unprovable, dead contract.

## Root Cause

The WebUI runtime producer was removed, but its Shipwright verifier module,
phase dispatch, tests, and documentation were not removed with it; the retained
consumer therefore outlived the boundary it claimed to verify.

## Scope

- Remove the obsolete runtime verifier module and its unit tests.
- Remove `runtime` from the unified verifier CLI and `--phase all` dispatch.
- Update the Canon/pipeline and user-facing verifier documentation.
- Add a CLI-level integration regression proving the retired phase cannot be
  selected and no longer appears in help output.
- Leave `shared/scripts/dev_server/**` and the external WebUI unchanged.

## Acceptance Criteria

- [x] **AC-1-agent:** Invoking `verify_phase.py --phase runtime` exits non-zero and
  reports `runtime` as an invalid phase; the CLI help no longer advertises it.
- [x] **AC-2-agent:** `verify_phase.py --phase all` contains no runtime verifier
  import or dispatch, and a dispatch-level integration probe proves every
  remaining verifier phase retains its prior order.
- [x] **AC-3-agent:** Active docs and verifier package documentation contain no
  claim that `runtime_checks.py` or zombie PID reconciliation remains a
  supported Canon surface; historical changelog records remain untouched.
- [x] **AC-4-agent:** No file under `shared/scripts/dev_server/` changes.

## Verification (medium+)

- **surface:** `cli`
- **runner:** `uv run --python 3.11 --with pytest pytest integration-tests/test_verify_phase_cli.py -v`
- **evidence path:** `.shipwright/runs/iterate-2026-08-04-runtime-process-identity/surface_verification.json`
- **full suite:** `uv run shared/scripts/tools/run_test_suite.py --project-root . --run-id iterate-2026-08-04-runtime-process-identity`

## Spec Impact

`NONE` — this removes an obsolete framework verifier left behind by an
architecture change; no adopted-project functional requirement describes the
legacy WebUI governor.

## Confidence Calibration

- **Boundary inventory:** former producer = deleted WebUI process governor;
  consumer = `runtime_checks.py`; public dispatcher = `verify_phase.py`.
- **Composition probe:** invoke the real CLI and assert the retired selector is
  rejected, a surviving selector still loads, and the remaining `all` dispatch
  order is unchanged.
- **Negative probe:** scan active source/docs for `runtime_checks.py`,
  `pids.json`, `--phase runtime`, executable callers, imports/re-exports, and
  zombie-replay claims after the removal; immutable changelog history is
  explicitly excluded.
- **Stopping result:** exhausted. The real CLI regression was red before the
  removal and green after it; the active-source scan found no executable
  caller or stale import, and the targeted remaining-verifier suite passed.

## External Plan Review Findings

- **High — active callers:** accepted. Inventory workflows, hooks, task
  runners, source, and active docs before deletion; remove every executable
  caller or stop if it represents a still-required control.
- **Medium — surviving dispatch order:** accepted. The integration regression
  records the real dispatch order and asserts the exact remaining phase list.
- **Medium — stale imports:** accepted. Exercise `--help`, one surviving
  selector, and the `all` registry so package import drift cannot hide.
- **Low — dedicated integration file:** rejected with reason. The
  `cross_component` floor mechanically requires an integration-category
  behavior. The review's naming refinement is accepted: the durable test is
  the general `test_verify_phase_cli.py` contract rather than a retirement
  tombstone.
