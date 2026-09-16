# Mini-Plan: deploy-ac02-ac05-coded-gates

run_id: iterate-2026-09-16-deploy-ac02-ac05-coded-gates
complexity: small
type: feature

## Background

t5's test-backfill campaign (2026-09-12-t5-deploy-changelog-miniplan.md) left
FR-01.08/AC02 and FR-01.08/AC05 unbound with a recorded reason: both describe
SKILL.md agent prose (an `AskUserQuestion` confirmation gate, and an agent
deciding to invoke `rollback.py` after reading a failed smoke-test JSON) with
no coded artifact a test can drive. The reviewer's finding (glm #5, round 2)
flagged this as a real product gap, deferred as out of scope for a
test-backfill unit. This unit closes that gap with new production code, then
binds both ACs.

## Files to create/modify

- **NEW** `plugins/shipwright-deploy/scripts/lib/test_gate.py` — extract
  `validate-deploy.py`'s `_test_gate` logic verbatim into an importable
  `evaluate_test_gate(project_root, confirmed)` function, so a second coded
  gate (below) can share the identical oracle rather than re-deriving it
  ("one oracle" — the pattern this plugin's own verifiers already follow).
- **EDIT** `plugins/shipwright-deploy/scripts/checks/validate-deploy.py` —
  replace the inline `_test_gate` def with an import from `test_gate.py`.
  No behavioural change; existing tests (`test_validate_deploy.py`) prove it
  via subprocess/JSON-output, never the private function directly.
- **NEW** `plugins/shipwright-deploy/scripts/lib/release.py` — the coded
  release entry point:
  - `release(...)` refuses to call `jelastic_client.deploy_from_git` when
    `evaluate_test_gate` reports a failing/missing gate, unless
    `confirm_failing_tests=True` was passed (AC02: a structural refusal, not
    agent prose deciding whether to proceed).
  - After a successful deploy, when a `smoke_url` is supplied, runs
    `smoke_test.run_smoke_test` and — on failure, and only when a previous
    VCS ref was read back before deploying — automatically calls
    `rollback.rollback_git` with the previous ref and records the audit
    entry with `invocation="auto"` (AC05: a coded trigger, not an agent
    reading JSON and deciding to run `rollback.py`).
  - CLI (`argparse`): `--env-name`, `--repo-url`, `--branch`, `--context`,
    `--project-root` (required, same rationale as `rollback.py`),
    `--confirm-failing-tests`, `--smoke-url` (optional — omitting it skips
    smoke+auto-rollback entirely, matching a bare `deploy` today),
    `--profile` (deploy profile, feeds both the smoke policy and the
    data-drift strategy the same way `rollback.py --profile` already does),
    `--migrations-dir`.
  - Exit codes: `2` refused before contacting the host (test gate);
    `0` released (smoke skipped, or smoke passed); `1` deployed but smoke
    failed (rollback attempted or not — the release did not end clean).
- **NEW** `plugins/shipwright-deploy/tests/test_release.py` — unit coverage
  for `release()`: gate refusal / gate-confirmed pass-through / smoke-pass /
  smoke-fail-triggers-auto-rollback / smoke-fail-with-no-previous-ref-skips-
  rollback, using a fake `JelasticClient`-shaped stub (no real HTTP).
- **NEW** `plugins/shipwright-deploy/tests/test_release_e2e_cli.py` —
  subprocess E2E against a real local HTTP stub (mirrors
  `test_rollback_e2e_cli.py` / `test_smoke_e2e_cli.py`'s own pattern): proves
  the refusal never sends a request to the stub, and that a failed smoke
  check against a real dead URL produces a stub-recorded `editproject` call
  pinning the previous ref (the auto-rollback actually reaching the host).
- **DOC** `plugins/shipwright-deploy/skills/deploy/SKILL.md` — add a short
  "Non-interactive Release Path" note documenting `release.py` as the coded
  equivalent for automated/CI invocations, without altering Steps 2-5's
  existing interactive flow (which stays untouched: ASK-FIRST for PROD is a
  constitution invariant, and Steps 3-5's ordering around
  `append_phase_history`/canon events is unrelated to this gap).

## Test strategy

- Unit tests drive `release()` directly against a stub client object
  (fast, no subprocess) for every branch above.
- One E2E subprocess test per AC, following this plugin's own established
  "deliberately unmocked, real local HTTP stub" pattern, so the two new ACs
  are proven the same way every other bound AC in this plugin already is.
- No E2E needed for the web surface (backend-only Python change,
  `touches_build`/UI not applicable) — F0.5 surface = `none` with
  justification.

## Alternative considered

Extending `jelastic_client.py`'s existing `deploy` CLI subcommand in place,
rather than a new `release.py`. Rejected: `rollback.py` already imports
`jelastic_client` (lazily, inside `_client()`), so `jelastic_client.py`
importing `rollback`/`smoke_test` at module level would put deploy's lowest-
level API wrapper in a cycle with the module that already depends on it.
`release.py` sits above both and can import either without one owning the
other's concern.
