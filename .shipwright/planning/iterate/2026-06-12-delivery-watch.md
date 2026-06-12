# Iterate Spec — Delivery-Watch: no "shoot and forget" (delivered = merged + green)

- **Run ID:** iterate-2026-06-12-delivery-watch
- **Intent:** CHANGE (F11 contract: arm auto-merge → WATCH to delivery, not "STOP at armed")
- **Complexity:** medium (framework prose contract + new helper + F0 gap close + tests/docs)
- **Origin:** 2026-06-12 PR #213 was reported "done / auto-merge armed" while CI was RED — an
  over-budget `architecture.md` entry failed the iterate-plugin 600-char agent-doc budget gate
  (`test_agent_doc_entry_rules`), which is NOT in the `shared/tests -m "not cross_plugin"` F0 run.
  Auto-merge stalled; the user caught it. See memory `feedback_no_shoot_and_forget`.

## Problem (two compounding gaps)

1. **Shoot-and-forget:** F11 ends at "PR armed for auto-merge" and declares the run done.
   If a Required Check then fails, the PR sits BLOCKED and nobody notices — "delivered" was
   claimed on an un-merged, red PR.
2. **F0 content-lint blind spot:** local F0 runs `shared/tests` only, so content-lints that
   gate F2/F3a outputs (the iterate-plugin agent-doc 600-char budget; artifact-path-canon) do
   NOT run locally → red CI slips through.

## Decision

**"Delivered" = the PR is actually MERGED with all Required Checks GREEN**, confirmed by
watching the PR to a terminal state. Encode it:

1. New helper `shared/scripts/tools/watch_pr_delivery.py`: a pure `classify_delivery(pr_json)`
   (merged / closed / checks_failed / pending) + a `watch()` poll loop over
   `gh pr view --json state,mergeStateStatus,statusCheckRollup`. Exit 0 merged · 2 checks_failed
   (lists the failed checks + URLs) · 3 closed · 4 pending-timeout. Host-specific (gh) — the watch
   is inherently about GitHub PR state; the iterate's host-agnostic guarantees are unaffected.
2. F11.md: replace "This run STOPS here" with a **Delivery Watch** step. Delivered ONLY on
   `merged`. On `checks_failed` → STOP (not delivered): diagnose, fix, re-push, re-watch.
3. F0/F2: must run the content-lints that gate F2/F3a outputs (iterate-plugin
   `test_agent_doc_entry_rules`, `test_artifact_path_canon`) before push — not just `shared/tests`.

## Spec Impact

MODIFY — changes the F11 finalization contract + the F0 verification scope. No FR delta.

## Affected Boundaries

- `watch_pr_delivery.classify_delivery` JSON contract (`{status, failed?, mergeState?}`) — the
  producer/consumer boundary the F11 prose parses (round-trip tested with fake gh payloads).
- Runtime-prompt prose: `references/F11.md`, `references/F0.md`/`F2.md`, `SKILL.md`, docs.

## Approach

1. `watch_pr_delivery.py`: pure `classify_delivery(pr_json)` (unit-testable, no gh) + `watch()`
   (gh + sleep + classify) + `main()` CLI. A check is failing iff a CheckRun conclusion ∈
   {FAILURE, CANCELLED, TIMED_OUT, STARTUP_FAILURE, ACTION_REQUIRED} or a StatusContext state ∈
   {FAILURE, ERROR}; pending = OPEN with no failures yet.
2. F11.md delivery-watch step + drift test.
3. F0/F2 content-lint reinforcement + the existing-memory tie.
4. docs/hooks-and-pipeline.md + SKILL F11 index.

## Acceptance Criteria

- [ ] `classify_delivery` returns merged/closed/checks_failed/pending for the matching gh payloads
      (incl. a payload with one FAILURE CheckRun → checks_failed listing that check).
- [ ] F11.md no longer says the run is done at "armed"; it runs `watch_pr_delivery.py` and treats
      delivered = merged (drift test).
- [ ] F0/F2 prose requires the iterate-plugin agent-doc budget lint before push (drift test).
- [ ] Full F0 suite green (incl. the iterate-plugin content-lints this time); no new bloat crossing.
- [ ] DOGFOOD: this PR is watched to merged+green before "delivered" is claimed.

## Confidence Calibration
- **Boundaries touched:** {filled before F0}
- **Empirical probes run:** {filled before F0}
- **Test Completeness Ledger:** {table below}
- **Confidence-pattern check:** {filled before F0}

### Test Completeness Ledger
| Behavior | Disposition | Evidence / reason_code |
|---|---|---|
| classify_delivery → merged on state=MERGED | tested | classifier test |
| classify_delivery → closed on state=CLOSED | tested | classifier test |
| classify_delivery → checks_failed on a FAILURE CheckRun (+lists it) | tested | classifier test |
| classify_delivery → pending on OPEN with running/clean checks | tested | classifier test |
| StatusContext FAILURE/ERROR counts as failing | tested | classifier test |
| watch() poll-loop against a live PR | untestable | requires-external-nondeterministic-service (gh+GitHub); the pure classifier is the tested core |
| F11 runs the delivery-watch (delivered=merged) | tested | F11 drift test |
| F0/F2 requires the agent-doc budget lint | tested | F0/F2 drift test |
