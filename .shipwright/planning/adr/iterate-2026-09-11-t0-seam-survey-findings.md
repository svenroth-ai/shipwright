# t0 seam survey — review findings ledger (campaign req3-05-test-backfill-mono)

## Context

Campaign `req3-05-test-backfill-mono` (REQ3.05, mono test-backfill anchor) needs one
repo-wide answer to "which existing test seam does a backfilled test for FR-01.NN attach
to" before its nine work units (t1–t9) can run without each re-deciding the same question.
t0 is that BLOCKING, read-only survey unit — no AC cluster of its own
(`FR cluster: -` in its spec).

## Decision

Produce `.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md`: a master FR→root
mapping table (all 20 FR-01.NN clusters), derived from `spec.md` AC text, the current
`shipwright_ac_coverage_baseline.json`, and `grep`-plus-spot-check precedent for every
already-bound AC (`@pytest.mark.covers("FR-xx/ACnn")`). Two named exceptions (FR-01.12
`/shipwright-preview`, FR-01.15 cross-repo output contract) get AC-by-AC breakdowns because
no single existing seam covers either FR's full AC list. Placed at a TRACKED path — not the
gitignored `campaigns/` planning directory — because it is a durable cross-unit reference,
unlike `campaign.md`/`status.json`. A pointer stub + `campaign.md` note give in-worktree
discovery from the (gitignored) campaign folder.

**No architecture impact (F2 no-op, justified):** no new route, component, schema, service,
write-surface, read-surface, or convention was introduced — this is a read-only analysis
document. `architecture.md` is not touched.

## Self-Review (7-item checklist, ADR-029)

All 7 items PASS (2 marked N/A for non-applicable axes — no runtime code, no tests added).
See `record_review_pass.py` `self` row (`iterate-2026-09-11-t0-seam-survey`) for the
machine-readable record; summary: Spec Compliance (pass — scope mismatch between t0's actual
mandate and the shared t1-t9 AC-checklist boilerplate is documented, not silently papered
over), Error Handling (n/a), Security Basics (pass), Test Quality (n/a — t0 is read-only per
its own spec), Performance Basics (n/a), Naming & Structure (pass — follows the
`2026-07-15-test-traceability-layers/TT8-coverage-delta.md` precedent), Affected Boundaries
ADR-024 (pass — no serialized format crossed a boundary; the baseline JSON was read-only).

## External-Plan-Review-Findings (Step 3.5, `--mode iterate`, glm + openai/codex)

Both providers responded (glm: approve; openai: revise). High/medium findings, disposition:

| # | Source | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | t0's "read-only, no ACs" framing conflicts with the spec's own boilerplate AC checklist (tests + baseline regen) | rejected-with-reason: `FR cluster: -` in t0's own spec — no cluster to bind; boilerplate is a shared template not tailored per unit (identical across t1-t9); documented as a "Scope note" + a spec-authoring gap in the survey header, not invented binding work |
| 2 | openai | high | several rows still require the unit to pick its own seam, defeating the point of a shared survey | accepted-and-fixed (partial): added a "Quick-decide notes" section with a one-sentence decision rule per multi-root FR, plus full AC-by-AC tables for both Named Exceptions; rejected a full 259-AC appendix as disproportionate for a `small`-complexity BLOCKING unit |
| 3 | openai | medium | tracked file path / baseline-field mechanism for "recorded reason" not specified | accepted-and-fixed: named the tracked path explicitly; added Finding 5 documenting the baseline schema (v1, flat `unbound` list) has NO reason field — a real gap, out of t0's read-only scope to fix, flagged for t1-t9 |
| 4 | openai | medium | grep-derived precedent evidence, not execution-derived | accepted-and-fixed: added an explicit caveat distinguishing a throwaway `--collect-only` spot-check from the binding ADR-044 `--junitxml` invocation; spot-checked one row live (`shared/tests/test_phase_history.py`, 18 tests collected) |
| 5 | openai | medium | named exceptions don't define per-AC provable-vs-residual outcomes | accepted-and-fixed: both exceptions rewritten as AC-by-AC tables naming the provable assertion and the residual guarantee that is NOT provable without further work |
| 6 | openai | medium | FR-01.15's gate ACs need a named follow-on owner, not silent closure via library-only tests | accepted-and-fixed: survey now explicitly forbids closing AC02/03/06 via the library unit test alone and requires a tracked follow-up (triage card or decision-drop) naming an owner |
| 7 | glm | medium | root-count table (t8=5, t9=4) silently reinterprets the campaign's "never more than two" constraint as a "target" | accepted-and-fixed: reframed as an explicit flagged deviation for the campaign owner to resolve (two honest options named), not a unilateral reinterpretation by t0 |
| 8 | glm | medium | Exception 2's "recorded reason" has no machine-checkable home, risking bit-rot into unlinked prose | accepted-and-fixed (partial): documented as Finding 5 (baseline schema gap); rejected adding a new `unbound_reason` baseline field as out of a read-only survey's scope — that is real development work for whichever unit takes it |

Low-severity findings (both providers) also addressed: count columns marked
snapshot/non-normative (glm); bare `covers("FR-01.NN")` tags flagged as needing
`/ACnn` qualification before they count (glm, Finding 6); Exception 1's AC-bucket
assignment made explicit rather than deferred (glm).

Recorded via `record_review_pass.py record --review-type plan --status completed
--provider openrouter --from external-review-json` (12 findings parsed) and
`--review-type plan_internal --status not_run --disposition "no internal arm — see
project_plan_review_has_no_internal_arm"`.

## External-Code-Review-Findings (Step 3.7 item 2, `--mode code`, glm + openai/codex)

Both providers responded (glm: revise; openai: revise) against the single tracked diff
(`.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md`, new file). High/medium
findings, disposition:

| # | Source | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | baseline not regenerated despite the spec's literal AC checklist | rejected-with-reason: same as plan-review #1 — t0's `FR cluster: -` means running the regenerator now is a no-op that would misrepresent zero source/test changes as work |
| 2 | glm | medium | header claims a pointer stub exists at the campaign path, but the diff (rightly) shows no such file — unverifiable from the diff alone | accepted-and-fixed: reworded the header to state explicitly that the stub and the `campaign.md` note are NOT diff-visible (both paths gitignored) rather than asserting them as if the diff could confirm it |
| 3 | glm | medium | the "recorded reason" AC (per-unit exit condition) is only partially satisfied — reasons exist as prose here, not attached to any baseline entry | accepted-and-fixed: added an explicit paragraph naming the two Named Exceptions as the recorded reason for their specific AC ids, and requiring t8/t9 to cite this file by section when they record those ids as unbound-with-reason |
| 4 | openai | medium | the caveat's suggested `pytest <root>/<file> -q` spot-check (no `--junitxml`) reads as if it could substitute for the binding one-invocation-per-root ADR-044 requirement | accepted-and-fixed: reworded to state explicitly the spot-check is a throwaway private probe, never a substitute for the real `--junitxml` invocation |
| 5 | openai | medium | FR-01.12/AC01 was left partially mapped — the "build ready" precondition half had no recorded no-seam reason, unlike AC02/03/07/09 | accepted-and-fixed: AC01's table row now explicitly names the precondition half as sharing AC02's identical no-seam reason |
| 6 | openai | medium | t8 (5 roots) / t9 (4 roots) exceed the campaign's binding "never more than two" cut; a blocking survey should give a compliant mapping or a secured amendment, not defer | rejected-with-reason (already substantially addressed by plan-review disposition #7): t0 has no authority to unilaterally re-cut campaign.md's Sub-Iterates table (itself out of a read-only survey's scope) or to waive a binding constraint; the survey already names the concrete choice, recommends one, and flags the conflict for the campaign owner explicitly rather than silently overriding it |

Low-severity finding (glm): unverified precedent files — already mitigated by the caveat
(mitigation judged adequate by the same review). Internal arithmetic cross-check (glm):
verified the 20 per-FR unbound counts sum to 259 and the 4-FR/9-bound-AC claim in Finding 2
— consistent.

Recorded via `record_review_pass.py record --review-type external_code --status completed
--provider openrouter --from external-review-json` (7 findings parsed).

## Confidence Calibration

Skipped — effective complexity `small`, no `touches_io_boundary` risk flag, not invoked
explicitly. Self-Review (above) is the only review axis besides the plan/code review
cascade for this run.

## Corrective pass (Stage-1 spec-reviewer REJECT, 2026-09-11)

The orchestrator's Stage-1 spec-reviewer (3f-bis cascade, run against the merge-base diff
of the first pushed commit `e95c49cd7`) REJECTed PR #720 with two findings. Both were
independently re-verified before acting, per this campaign's standing "verify the claim,
not its neighbourhood" discipline:

1. **Confirmed real — under-reported escalation.** The survey's "Flagged deviation"
   paragraph and triage card `trg-ff6ea5f0` named only t8 (5 roots) and t9 (4 roots) as
   violating campaign.md's "never more than two test roots" rule. Re-checking every row of
   the "Per-unit ADR-044 root count" table systematically (not spot-checked) confirmed t4
   (3 roots: `shipwright-test/tests`, `shipwright-security/tests`, `shared/tests`) and t5
   (3 roots: `shipwright-deploy/tests`, `shipwright-changelog/tests`, `shared/tests`) also
   exceed the cap — the table data already showed this; only the prose and the triage card
   under-reported it. **Fixed:** rewrote the paragraph to name all four units and restated
   the accept/re-cut framing for each; amended `trg-ff6ea5f0` in place via
   `triage_cli.py amend` (append-only ledger — an amend event, not a new card) to the same
   effect. No other unit among t1-t9 exceeds two roots.

2. **Investigated and found to be a false positive — not restored.** The finding claimed
   commit `e95c49cd7` deleted a "foreign" evidence file belonging to a different, completed
   run (`.shipwright/agent_docs/iterates/iterate-2026-08-26-b-pure-hardening.json`),
   allegedly still present on `origin/main`, via an overbroad stage (`git add -A`). Forensic
   re-check before acting: (a) `origin/main`'s current tip does NOT contain the file
   (`git ls-tree` returns nothing); (b) the file WAS present at this branch's original
   merge-base (`4a977c53f5fd`); (c) an independent, already-merged sibling PR (#721,
   commit `c6bf0805c`) deleted the identical file between that merge-base and the current
   `origin/main` tip, via its own F5c retention eviction — the same designed, self-healing
   mechanism this run's own F5c triggered (`.shipwright/agent_docs/iterates/` held 53
   unpinned summary entries at the merge-base, already over the ~50 cap); (d) the file is
   not in `shipwright_run_config.json`'s `iterate_retention_pins`; (e) this run never used
   `git add -A` at any step (all `git add`/`git restore` calls named explicit paths). The
   suggested restore command (`git checkout origin/main -- <path>`) fails as tested
   (`pathspec ... did not match any file(s)`), because there is nothing on `origin/main` to
   restore — resurrecting the file from the stale merge-base blob would reintroduce content
   `origin/main` has already, independently and correctly, retired. **Resolution:** rebased
   this branch onto the current `origin/main` (bringing in PR #721) instead of restoring
   anything; once rebased, both sides agree the file is absent, so it no longer appears in
   the branch's diff at all — the original appearance was a three-dot/merge-base diff
   artifact of reviewing before this branch had absorbed #721, not a mistaken deletion by
   this run.

Both fixes verified via a fresh `git diff origin/main...HEAD --stat` after rebase: the
disputed path no longer appears; the corrective diff is scoped to the seam-survey prose,
the triage amend event, and this note.

## Review cascade delegation (Step 3.7 item 1)

`spec`, `code`, `doubt` recorded `not_run` / `delegated_to_orchestrator` — this runner's
tool set (Read, Write, Edit, Bash, Glob, Grep) excludes `Agent`, so it cannot spawn the
internal reviewer cascade. The campaign orchestrator runs it at loop step 3f-bis, before
merge, and promotes these rows with `--force`.
