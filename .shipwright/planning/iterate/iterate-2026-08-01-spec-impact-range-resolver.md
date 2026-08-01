# Iterate — the spec-impact gate sees the branch, not the tip

- **Run-ID:** `iterate-2026-08-01-spec-impact-range-resolver`
- **Intent:** BUG (Path C) — an F11 gate FAILs a run that satisfied it
- **Complexity:** medium (locked; `prior_source: keyword`, confidence 0.70)
- **Measured in:** `iterate-2026-07-31-it1-s2-expected-status`
- **Same class as:** PR #503 (`dcf85f87`), which converted four sibling gates and
  left this one behind

## Spec Impact

**NONE.** A verifier is repaired to measure what it always claimed to measure.
No FR changes, no `spec.md` is touched, no user-visible behaviour of the product
changes — only the gate's own answer on an input it was reading wrongly.

`change_type: tooling` · affected FRs: none.

## Symptom vs expected (F-debug Phase 1)

`check_spec_impact_recorded` reported, verbatim:

> `intent=feature iterate but commit <sha8> touched no .shipwright/planning/**/spec.md`
> `and recorded no spec_impact=none — classify the spec impact (ADD/MODIFY/REMOVE)`
> `or record spec_impact=none with a justification`

for a run whose iterate commit **did** touch a planning `spec.md`. It passed only
when re-run by hand against the pre-merge commit.

- **Error site:** `shared/scripts/tools/verifiers/iterate_checks.py:969` (the FAIL return).
- **Error source:** `iterate_checks.py:955` — `_commit_changed_paths(project_root, event_commit)`.
- **Expected:** the gate passes when *the iterate branch* touched a planning `spec.md`.

## Root cause (F-debug Phase 3 + 4)

Not a regression of this function — it has read one commit since it was written
(`iterate-2026-05-16-spec-impact-gate`). What changed underneath it is the F11
**ordering**: `ensure_current` (integrate-if-behind) runs *before* the verifier, and
the verifier is invoked with `--commit "$(git rev-parse HEAD)"`. On a branch that was
behind, HEAD is then the integration **merge commit**, and a merge commit's own
changed-path set holds only the conflict-resolved files.

Measured on the citing run: **4 paths** in the merge commit's own set, **36** in
`merge-base..HEAD`. The spec.md the iterate wrote was in the 32 that fell out.

The boundary at which good input becomes bad output is exactly one call:
`git show --name-only <merge-commit>` prints the conflict-resolution set, not the
branch's work. In the worktree flow this is unavoidable, because F5b records the
`work_completed` event with `commit: ""` — so `event_commit` falls back to the
caller-supplied HEAD, which is the merge.

`dcf85f87` (#503) named this blindness a *property of the F11 ordering, not of any
single check*, put the range view in `git_helpers._iterate_changed_paths`, and
converted `derived_snapshot_gate`, `integration_coverage`, `ci_supplychain` and
`decision_log_gate`. `iterate_checks.py` is not in that commit's diff. This gate is
the last single-commit consumer among the F11 gates.

### Scope check — what is *not* the same class

`spec_checks.py` (S9/S10) also reads `--name-only`, but through
`git log -n10 --name-only`: a *window over recent history*, which already contains
the iterate commit whatever sits on top of it. Different mechanism, Tier-2 WARN,
not this defect. Deliberately untouched.

`layer_coverage.check_cross_layer_coverage` is already range-based via its own
`_merge_base` / `regenerate_base_head`. No change needed.

## The fix

Route the changed-path lookup through `_iterate_changed_paths`, anchored — as
today — at `event_commit`, not at the caller's `commit_hash`.

**The anchor is the load-bearing detail.** `event_commit` is the F7-referenced
commit, falling back to `commit_hash`. Re-anchoring at `commit_hash` would look
tidier and matches the siblings' call shape, but it breaks the multi-commit
contract pinned by
`test_spec_impact_resolves_event_by_run_id_in_multi_commit_iterate`: that test
puts the spec.md in the F6 commit and a no-spec follow-up at HEAD, and requires
the gate to answer for the F6 commit. Keeping `event_commit` fixes the merge-HEAD
case (where `event_commit` *is* HEAD, because F5b wrote `commit: ""`) without
touching the case the siblings never had to model.

**A second, free correction rides along.** `_commit_changed_paths` returns `[]` for
a merge commit, and `[]` reads as "touched nothing" → **FAIL**.
`_iterate_changed_paths` folds that blind case into `None`, and the existing
`changed is None` branch already returns SKIPPED. So where the gate cannot see, it
now says so instead of accusing. That is the documented posture of every sibling.

## Acceptance Criteria

- **AC1** — With HEAD an integration merge commit and the branch's own commit
  carrying a planning `spec.md`, the gate PASSES.
- **AC2** — The gate does not blame the branch for a `spec.md` that arrived from
  mainline through the merge: a branch that touched no spec, merging a main that
  did, still FAILs.
- **AC3** — The multi-commit contract is unchanged: event references the F6 commit,
  HEAD is a later no-spec commit, spec.md in F6 → PASS.
- **AC4** — A diff the gate cannot obtain is SKIPPED, never FAILed and never passed.
- **AC5** — The detail names the iterate's **work up to** the anchor, not "commit
  `<sha>`", which is what made the report unactionable: the operator inspected the
  named merge commit, found no spec.md there, and had no way to see the gate was
  asking the wrong question.

  *Revised during Stage-2 review.* The first wording said "this iterate's branch",
  which is itself an over-claim: the resolver has three views — the branch range,
  the branch **prefix** ending at `event_commit`, and the single-commit fallback
  when no corroborated trunk base exists (which is the view every pre-existing test
  takes). "Work up to `<sha>`" is true in all three. Trading one inaccurate subject
  for another would have re-created this defect with the polarity flipped.

## Accepted limitation — the widening is fail-OPEN here (Stage-3 finding)

**The "same class as the siblings" argument does not survive a polarity check, and
Stage-3 review caught that it was doing work it could not do.** All four gates #503
converted use the changed set as a violation *trigger* — `derived_snapshot_gate`,
`decision_log_gate`, `integration_coverage`, `ci_supplychain` all ask "is a
forbidden thing in here?", so a wider range can only find *more*: fail-safe. This
gate uses the changed set as evidence of *compliance* — "is a spec.md in here?" — so
a wider range can only fail *less*: fail-open. Same blindness, opposite risk.

The reachable consequence is the `stacked` campaign strategy
(`autonomous_loop.VALID_STRATEGIES`, `branch_base.py:61`), where unit N branches off
unit N-1's still-unmerged branch. `_branch_base_commit` anchors on the trunk, so
N-1's commits fall inside N's range: if N-1 wrote a planning `spec.md` and N wrote
none, **N's gate now passes on N-1's file**, where the single-commit view would have
failed it. Verified, not theorised — `test_a_spec_md_from_a_FOREIGN_commit_in_the_
range_satisfies_the_gate` builds that exact topology and passes.

**Accepted, not fixed, for this iterate.** The fix Stage 3 proposed — intersect the
range with commits carrying this run's `Run-ID:` trailer — would make this the only
one of the five gates that does so, while all five share the same trunk-anchored
base; a divergence like that belongs in a change that treats the family, not in a
bug fix to one member. Under `serial` (the default: a worktree forked from freshly
fetched `origin/main`) the range holds only this unit's work and the hole is closed
by construction. The behaviour is pinned by a test that documents itself as
asserting a weakness, so it cannot drift silently.

Surfaced to the operator in the F12 summary as the one follow-up this run
deliberately did not take.

## Alternatives considered

1. **Re-anchor at `commit_hash` for symmetry with the siblings.** Rejected — see
   above; it regresses a pinned multi-commit test to buy call-shape uniformity.
2. **Make F11 pass the pre-merge commit instead.** Rejected — it re-opens the
   blindness for the four gates #503 already fixed, and F11's integrate-before-verify
   ordering is deliberate (you verify what will actually merge).
3. **Have `ensure_current` record the post-merge commit onto the event.** Rejected —
   larger blast radius (F5b/F6.5 contract), and it fixes the symptom for one gate
   while leaving the resolver asymmetry that produced it.
4. **Do nothing; document the workaround (re-run against the pre-merge commit).**
   Rejected — that is what the citing run had to do by hand, and a gate whose green
   depends on an operator knowing to re-anchor it is not a gate.

## Confidence Calibration

- **Boundaries touched:** the git changed-path boundary between
  `verifiers/iterate_checks.py` and `verifiers/git_helpers.py`. No IO/serialization
  boundary — no `*_config.json`, `.env` or hook file is in the code diff, so
  `touches_io_boundary` is correctly not raised.
- **Empirical probes run:**
  - Probe 1 — built the real F11 shape in a git repo with a bare `origin`
    (branch commit touches spec.md → main moves → `merge --no-ff origin/main`) and
    asserted the merge commit really is a merge (3 entries from
    `rev-list --parents -n1`). The gate FAILs before the fix, PASSes after.
    *Finding: reproduces 100%; confirms the merge-HEAD path, not a theory.*
  - Probe 2 — inverted the fixture so **main** carries the `spec.md` and the branch
    carries none. *Finding: still FAILs after the fix — the range is measured from
    the merge-base, so mainline's work sits on the base side and cannot launder a
    missing spec into a pass.* This is the false-green the widening could have
    introduced, and it does not.
  - Probe 3 — ran the pre-existing multi-commit / legacy tests unchanged against the
    fixed code. *Finding: all pass; `_branch_base_commit` returns `None` in a
    remote-less fixture (only one trunk name resolves, and it refuses an
    uncorroborated base), so those tests take the single-commit fallback exactly as
    before.* **Scoped claim, corrected after Stage-3 review:** this establishes the
    fix is inert *against those fixtures*, which all take the fallback — NOT that it
    is inert in general. It is not: an add-then-revert of a `spec.md` within one
    branch nets out of `git diff` and now FAILs where the single-commit view of the
    revert commit passed. That is the better answer (the branch contributes no net
    spec change) but it is a real behaviour change, recorded here rather than
    implied away.
  - Probe 4 — audited every changed-path reader under `verifiers/` for the same
    class. *Finding: `iterate_checks.py:955` was the only remaining
    `_commit_changed_paths` consumer; `spec_checks.py` uses a 10-commit log window
    (different mechanism); `layer_coverage` is already range-based.*
  - Probe 5 — measured every changed file against the bloat rules. *Finding:
    `iterate_checks.py` sat at exactly its ceiling (`current: 1087`, ADR-093
    exception), so the first draft's +33 lines of prose would have HARD-BLOCKED the
    commit. Rewritten to land at exactly 1087 — the functional change is a one-token
    call swap and now costs zero net lines.* **Stage-3 correction:** the green
    `pre-commit` run does NOT clear the new test module. `anti_ratchet` blocks only
    paths already IN the baseline, so a brand-new file is structurally invisible to
    it — and the module had reached 301 lines against `LIMIT_SOURCE = 300`, i.e. a
    Group-H crossing that would surface post-merge with the hook still green. Split
    into `test_spec_impact_branch_range.py` (196) + `test_spec_impact_range_limits.py`
    (204), both comfortably under. Measured, not assumed.
- **Test Completeness Ledger:** below.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the repro is the F11 shape itself — a real merge commit made
    by git, not a stub returning a path list. The assertion that the fixture really
    built a merge is in the test, so the test cannot silently stop testing the bug.
  - *Breadth:* both directions are covered (sees the branch / does not blame main),
    plus the unavailable-diff posture and the untouched multi-commit contract.
  - *Integration composition:* not applicable — `cross_component` is not raised, and
    `risk_detectors.py:184` excludes the gate's own meta-tooling from that flag by
    design (gating itself would be circular).

### Test Completeness Ledger

| # | Behaviour this diff introduces / changes | Disposition | Evidence |
|---|---|---|---|
| 1 | Gate passes when the branch's own commit touched a spec.md and HEAD is an integration merge (AC1) | `tested` | `test_the_gate_sees_a_spec_md_carried_by_an_earlier_commit` — PASS |
| 2 | Gate does not inherit a spec.md that arrived from mainline via the merge (AC2) | `tested` | `test_the_gate_is_not_satisfied_by_a_spec_md_that_came_from_MAIN` — PASS |
| 3 | Multi-commit contract preserved: answer anchored at the F7-referenced commit (AC3) | `tested` | `covered-by-existing-test` → `test_spec_impact_resolves_event_by_run_id_in_multi_commit_iterate` — PASS, unmodified |
| 4 | An unobtainable diff is SKIPPED, not FAILed and not passed (AC4) | `tested` | `test_a_diff_the_gate_cannot_obtain_is_SKIPPED_not_failed` — PASS |
| 5 | Detail names the iterate's work, not the commit (AC5) | `tested` | `_assert_names_the_work_not_the_commit`, called from the AC1 and AC2 tests |
| 6 | Range resolution is genuinely used (not accidentally still single-commit) | `tested` | `test_the_gate_reads_the_branch_range_not_the_single_commit` — pins the call site against the resolver |
| 7 | An empty-but-RESOLVED range still FAILs — `None` and `[]` stay distinct | `tested` | `test_an_empty_but_trustworthy_range_still_FAILS` — added in Stage-2 review to kill a surviving mutation |
| 8 | A foreign commit's `spec.md` inside the range satisfies the gate (accepted fail-open) | `tested` | `test_a_spec_md_from_a_FOREIGN_commit_in_the_range_satisfies_the_gate` — pins the accepted limitation above |
| 9 | The BLIND skip announces itself, so a silent ERROR gate is visible | `tested` | asserted in `test_a_diff_the_gate_cannot_obtain_is_SKIPPED_not_failed` |
| 10 | Add-then-revert of a `spec.md` within the branch now FAILs (net-zero range) | `untestable` → `covered-by-existing-test` | the same code path as row 7 (`[]`/no-spec-in-range → FAIL); a dedicated fixture would re-assert `_iterate_changed_paths`' `git diff` semantics, not this gate's logic |

Zero testable-but-untested behaviours.

**Rows 7–9 came from review, not from me.** Row 7: the mutation `if changed is None:`
→ `if not changed:` left the whole module green, so the `None`-vs-`[]` distinction
this change explicitly relies on was itself unpinned — an ERROR gate could have been
silently mutated into a skip (Stage 2). Rows 8–9: Stage 3 showed the widening is
fail-OPEN here where it is fail-safe in the four sibling gates, and that the skip
branch was silent on an ERROR gate.
