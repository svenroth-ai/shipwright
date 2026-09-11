# Iterate: Retention cap headroom for `.shipwright/agent_docs/iterates/`

**run_id:** iterate-2026-09-12-retention-cap-headroom
**Type:** change
**Complexity:** medium (scope keyword: cross-worktree/retention mechanism; Repo Scout confirms `cross_component` machinery — see below)
**Spec Impact:** NONE (No-FR / tooling — internal recency-cache tuning for
Shipwright's own iterate-history bookkeeping; not a documented product FR.
The `[Shipwright] Detected: CHANGE ... Affected FRs: FR-01.14` hook match is a
false positive — FR-01.14 is the Triage Inbox requirement, unrelated to
retention; verified against `.shipwright/compliance/test-traceability.json`.)

## Problem

`shared/scripts/tools/append_iterate_entry.py`'s `ITERATE_RETENTION = 50`
prunes the oldest unpinned `.shipwright/agent_docs/iterates/<run_id>.json`
summary on every `append_iterate_entry` call once the unpinned count exceeds
the cap. Each iterate branch computes the victim set from whatever it can see
at its own fork point / last sync, so under higher branch concurrency than
the mechanism was sized for, different branches prune different — and
increasingly numerous — "victim" files belonging to *other* runs, and the
deletions land in `origin/main` as an incidental side effect of an unrelated
PR (e.g. `#726`'s squash deleted
`iterate-2026-08-26-fr-table-text-from-named-col.json` while merging an
unrelated plan/design change).

This was already investigated once:
`.shipwright/planning/adr/iterate-2026-08-15-retention-cap-parallel-merge-retention-approximate.md`
found `_apply_retention` re-reads the full on-disk set on every call, so an
overshoot self-heals on the very next append, and is bounded to "~1 entry
over cap per branch that overshot together in the same merge" — sized for
about 2 concurrent branches. That ADR explicitly declined to add new
merge-time/periodic-sweep machinery, on the grounds the self-heal already
covers the modeled case.

**What has changed since:** branch concurrency is materially higher now —
`git branch -a | grep iterate/` currently lists dozens of open iterate
branches, several "locked" in active worktrees at once. A same-day
investigation (2026-09-11, corrected same day) measured `origin/main`
sitting at 54 entries against the cap of 50 and traced multiple branches
each pruning a *different* victim set of other runs' files as they moved.
The investigation's original claim that this caused simultaneous PR merge
conflicts was independently retracted the same day (`git merge-tree
--write-tree` showed all four PRs in question merge clean; GitHub's
`mergeable` flag was stale, not blocked) — **so this iterate does not claim
or fix a merge-conflict problem.** What stands is narrower and still real:
retention's per-branch, stale-view pruning is a form of silent cross-run
data deletion of other runs' summary files, and the self-heal model the
2026-08-15 ADR relied on was sized for roughly 2 concurrent branches, not
the current working set.

Verified on this run's fork point (`origin/main` @ `0cea78813`): 53 canonical
`<run_id>.json` summaries on disk, 2 pinned
(`iterate_retention_pins` in `shipwright_run_config.json`), so 51 unpinned
against a cap of 50 — i.e. already at the "+1" bound the prior ADR modeled
as its steady state, not the more dramatic overshoot the same-day
investigation measured a day earlier (self-heal is visibly doing its job
between merges). The residual risk is not today's count; it is that the cap
sits with effectively zero headroom against a concurrency level several
times what the mechanism was designed and tested for, so a future burst of
parallel finalizations remains one bad afternoon away from repeating the
same silent-deletion incident at a larger scale.

## Fix chosen (leverage order from the investigation, item 1 only)

Raise `ITERATE_RETENTION` from 50 to 200 — well above the current working
set (53 canonical entries + growth headroom) and well above realistic
concurrent-branch fan-out. No branch prunes under normal load, so the
generator stops firing without touching the pruning mechanism itself. Full
history remains available in `shipwright_events.jsonl` regardless of the
cap, per the existing docstring.

**Explicitly out of scope for this run** (from the same investigation,
items 2 and 3):

- Moving retention to a main-only post-merge step / dedicated maintenance
  command. This is the exact "new merge-time or periodic-sweep machinery"
  the 2026-08-15 ADR already weighed and declined to build; revisiting that
  call is a bigger architectural decision than a headroom bump and belongs
  in its own iterate if the raised cap turns out not to be enough.
- An F6/pre-commit guard refusing to stage a deletion of another run's
  entry file. Retention is *designed* to delete other runs' oldest entries
  — that is its only job — so a guard against that specific shape of
  deletion would need to distinguish "legitimate retention prune" from
  some other failure mode that this investigation never identified. Adding
  it now would risk silently defeating retention rather than fixing a bug.

## Confidence Calibration

- **Boundaries touched:** `.shipwright/agent_docs/iterates/` retention cap
  (a config constant, not an I/O boundary format — no `touches_io_boundary`
  risk flag: this changes a numeric threshold, not a parse/serialize
  contract).
- **Empirical probes run:**
  - Counted canonical entry files on `origin/main` fork point: 53 total, 2
    pinned, 51 unpinned vs. cap 50 (matches the "approximately 50" model).
  - Grepped all three retention test files
    (`test_retention_merge_overshoot.py`, `test_retention_race.py`,
    `test_append_iterate_entry.py`) confirming every assertion reads the
    `ITERATE_RETENTION` symbol, not a hardcoded `50` — raising the constant
    changes no test's pass/fail shape.
  - Re-verified the investigation's retracted claim (four PRs conflicting)
    against `git branch -a` / prior main-health tooling rather than
    re-asserting it — see "What has changed since" above.
- **Test Completeness Ledger:**

  | Behavior | Status | Evidence / reason_code |
  |---|---|---|
  | `ITERATE_RETENTION` raised to 200 | tested | `test_retention_cap_headroom.py::test_retention_constant_is_200` |
  | Existing retention/self-heal/race tests still pass at the new cap value | tested | full run of `test_retention_merge_overshoot.py`, `test_retention_race.py`, `test_append_iterate_entry.py` (symbolic `ITERATE_RETENTION` references, no hardcoding) |
  | Docstring / inline comment / F5c.md all state the new cap consistently | tested | `test_retention_cap_headroom.py::test_docs_state_current_cap` (greps the three prose locations for the literal `200`) |
  | Pinned entries still excluded from the raised cap's window | untestable | `covered-by-existing-test` — `test_append_iterate_entry.py`'s pin-exclusion tests are cap-value-agnostic and already assert this against the (now 200) `ITERATE_RETENTION` symbol |

- **Confidence-pattern check:** asymptote — the fix is a single constant plus
  its three prose mirrors (module docstring, inline comment, F5c.md), all
  covered by an added regression test; no cross_component integration
  behavior applies here since this run does not touch merge/churn/hook/
  campaign-drain machinery, only the retention constant those systems read.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Findings:**
  - completeness/medium: repo-wide grep for the old cap missed two stale
    mentions phrased differently — `docs/hooks-and-pipeline.md:4466` and
    `docs/guide.md:1889,2374` — both describing `append_iterate_entry.py`.
    **Disposition: fix.** Both updated to 200; both now guarded by new
    tests (`test_hooks_and_pipeline_doc_states_current_cap`,
    `test_guide_doc_states_current_cap`).
  - performance/low: `_apply_retention`'s full-directory re-read now scans
    up to ~200 files/call instead of ~50, a direct consequence of the bump.
    **Disposition: disclose** — negligible at this file count; noted in
    the ADR's Consequences so it isn't rediscovered later.
- **Known limitations:** the per-call directory-scan cost above.
- **Status:** 1 fixed, 1 disclosed.

## Architecture Review

`external_review.py --mode architecture` over `architecture_brief.md`
("nothing permanent" shape — this changes an existing constant, no new
standing mechanism). Both reviewers approved:

- **GLM:** approve. No new mechanism created; a constant bump is the right
  proportionate response. Findings (low severity): the fix defers rather
  than resolves the underlying per-branch-stale-view pruning, so state a
  concrete tripwire in the ADR for when this fix is deemed insufficient —
  addressed via the "Revisit trigger" section added to the ADR below.
- **OpenAI (via Codex CLI):** approve. No findings.

## Affected Boundaries

- `shared/scripts/tools/append_iterate_entry.py` (constant + docstring +
  inline comment)
- `plugins/shipwright-iterate/skills/iterate/references/F5c.md` (retention
  prose)
- `.shipwright/planning/adr/` (new ADR entry amending the 2026-08-15
  decision's steady-state assumption, not reversing its "no new machinery"
  call)
