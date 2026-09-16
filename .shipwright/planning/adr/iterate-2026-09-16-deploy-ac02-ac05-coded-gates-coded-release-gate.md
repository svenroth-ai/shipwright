# Coded release entry point for FR-01.08 AC02/AC05

## Context

FR-01.08's AC02 ("refuse a release on failing tests until a person
confirms") and AC05 ("auto-rollback on smoke-test failure") existed only as
`SKILL.md` agent prose — an `AskUserQuestion` step in the interactive
`/shipwright-deploy` skill, and an agent reading a smoke-test JSON and
deciding to invoke `rollback.py`. Neither had a coded artifact a test could
drive end to end, so both were untestable. Surfaced during the
`req3-05-test-backfill-mono` campaign's t5 unit, external code review round
2 (glm finding #5).

## Decision

Add `plugins/shipwright-deploy/scripts/lib/release.py`: a new, agent-free
CLI entry point (`uv run release.py --env-name ... --target {dev,prod} ...`)
that chains the same building blocks Steps 2-5 of the interactive skill call
individually — test-gate check, deploy, smoke verification, auto-rollback —
behind structural guarantees instead of agent judgement:

- **AC02**: `test_gate.py` (`evaluate_test_gate`, extracted verbatim out of
  `validate-deploy.py`'s original inline `_test_gate` so both callers read
  one oracle) is checked BEFORE any host contact. A failing/missing gate
  without `--confirm-failing-tests` refuses structurally —
  `jelastic_client.deploy_from_git` is never called.
- **AC05**: when `--smoke-url` is given, a failed post-deploy smoke check
  automatically calls `rollback.rollback_git` back to the ref live
  immediately before this deploy, recorded with `invocation="auto"` in the
  same audit trail a manual rollback writes.
- **PROD stays ASK-FIRST regardless of invocation path** (constitution): a
  required, no-default `--target {dev,prod}` argument (mirroring
  `rollback.py`'s own `--invocation` pattern) refuses `target=prod` without
  an explicit `--confirm-prod`, since this module has no agent in the loop
  to show an `AskUserQuestion` — the confirmation must come from whatever
  upstream process (a human-gated CI approval step, a campaign operator)
  invoked it.
- **Auto-rollback requires a configured polling deadline.** A single
  fixed-timeout smoke attempt (no `--profile` / `--smoke-max-wait`) is not a
  reliable enough signal to trigger a host mutation — `smoke_test.py`'s own
  docstring already warns a slow start-up would read as a failed release.
  Without a deadline, the failure is still reported but auto-rollback is
  skipped, naming the gap.
- **Post-rollback health recheck.** After a successful `rollback_git` call,
  the restored ref is re-smoke-tested and the result surfaced as
  `rollback_verified_healthy` — a confirmed ref pin is not the same claim as
  "serving traffic again".

## Consequences

FR-01.08 AC02 and AC05 gain a coded artifact 20 pytest tests can drive
in-process, plus 4 real-subprocess E2E tests proving the CLI wiring across a
process boundary — closing the exact gap flagged in t5's external review.
`_client()`/`_hosting_errors()` (previously duplicated between `rollback.py`
and this new module) are extracted to a shared `hosting.py`, so both callers
read one implementation. `release_rollback.py` holds the post-deploy
smoke/rollback decision, split out of `release.py` once that module crossed
the 300-line guideline.

## Rationale

Doubt-review (Stage 3, adversarial) raised 6 findings; two are fixed in code
(the deadline-required gate and the post-rollback health recheck above,
matching findings #2 and #5) and two more are fixed as documentation/wording
only (PROD guard is finding #3, fixed in code; the misleading skip-reason
wording is finding #6, reworded). The remaining two are recorded as known
limitations rather than fixed — see "Rejected" below.

## Known limitations (recorded, not fixed)

- **Auto-rollback restores a branch NAME, not a commit** (doubt finding #1).
  `jelastic_client.deploy_from_git` (pre-existing, unmodified by this unit)
  never re-pins the branch for an environment that already has a VCS
  project — only on first-ever creation. On the routine "push new commits
  to the same branch, CI redeploys" cycle, `previous_ref` already equals the
  deployed branch, so auto-rollback correctly reports it has nothing
  distinct to restore at commit granularity. Commit-level rollback needs a
  versioning/tagging scheme this module does not implement — a materially
  bigger design than this unit's scope. Documented in
  `skills/deploy/references/non-interactive-release.md`.
- **No lock across the whole gate→deploy→smoke→rollback sequence** (doubt
  finding #4). Concurrent `release.py` invocations against the same
  `env_name` are not serialized (matching `rollback.py`'s own pre-existing,
  unlocked assumption). Callers are expected to serialize releases per
  environment upstream (CI/campaign convention), not invoke this
  concurrently for one target.

## Rejected

- **Extending `jelastic_client.py` in place** instead of a new `release.py`
  module — rejected: `rollback.py` already imports from `jelastic_client`,
  so a `release()` function living there importing `rollback.rollback_git`
  would create a circular import.
- **Fixing the branch-vs-commit rollback granularity now** — rejected as
  out of proportion to this unit's "small" complexity; needs a
  versioning/tagging scheme, not a coded-gate wrapper.
- **Adding a per-`env_name` lock now** — rejected for the same reason;
  `rollback.py` itself has never had one, and adding it only for the new
  entry point would leave the manual path with a different concurrency
  contract than the automated one.

## Follow-up (not actioned here)

`jelastic_client.deploy_from_git` never re-pins the branch for an
already-existing VCS project (pre-existing, untouched by this diff) — first
surfaced by code-reviewer, reinforced by doubt-reviewer as the root cause of
the branch-vs-commit rollback-granularity limitation above. Worth a future
iterate if commit-level auto-rollback is ever wanted.
