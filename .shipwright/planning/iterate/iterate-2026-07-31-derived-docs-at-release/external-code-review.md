# External code review — `iterate-2026-07-31-derived-docs-at-release`

Providers: `openai` (verdict **revise**), `gemini` (**unavailable** — its reply was
truncated mid-analysis by the provider; the salvageable part had reached no
finding). One of two succeeded, so this is recorded `completed` with a single
provider rather than claimed as a two-provider round. Raw payload:
`external-code-review.raw.md`.

All four findings are dispositioned. Three were real and are fixed.

---

## O-A (high) — `converge()` kept only the LAST pass's outcomes

**Finding.** If pass 1 reports an errored producer leg and a later pass succeeds,
the loop returns the final, all-green outcomes and `produce()` never sees the
failure. AC-4 is about *a* pass that failed, not the pass that happened to be
last.

**Real, and reachable.** An errored leg writes nothing, so the digest is
unchanged; the next pass can succeed and move it; the pass after that converges.
The failure is inside the loop and was being dropped on the way out.

**Fixed.** `converge` accumulates a `failures` map across every pass — first
verdict per path wins, as it is nearest the cause — and merges it over the final
outcomes. Pinned by `test_a_failure_in_an_EARLIER_pass_still_fails_the_run`, whose
fixture asserts it really converged on a later pass (`passes >= 3`) so it cannot
pass by accident.

## O-B (high) — a `ci-security.json` producer failure would fail the whole run

**Finding.** `failed_paths` included it, so an error there returned
`producer_failed` and no `ci_security` report — contradicting AC-6's "never fails
the run".

**Real as a contract defect, not currently reachable.** Checked:
`regenerate_tracked_snapshots` decides all seven from ONE `_update_compliance`
call, so `ci-security.json` cannot fail independently today, and its own failure
modes (`gh` unavailable, no fresh run) are fail-soft inside `refresh_ci_security`.
So AC-6 held **by accident of the producer's coupling** rather than by
construction — which is precisely the shape that breaks silently if that producer
ever reports per-path outcomes.

**Fixed anyway,** because the criterion is explicit: the path is carved out of the
refusal and its outcome is reported in `ci_security.producer_outcome` with
`stale: null`. Two tests: the carve-out, and
`test_a_tree_derived_failure_alongside_ci_security_still_refuses` so the carve-out
is for that one path and not a hole in the refusal.

## O-C (medium) — a refusal reset the documents to `HEAD`, discarding operator edits

**Finding.** `--stage` has no clean-tree preflight, yet every refusal called
`restore_to_head()`. An operator holding an uncommitted edit to a compliance
document would lose it while the tool cleaned up after a refusal that was not
their fault. The producer *inputs* were carefully snapshotted; the documents
themselves were not.

**Real — and it is the same defect Stage 1 found (MEDIUM-4) one level up**, which
is what makes it worth recording rather than just fixing: the first fix was
applied to the inputs and not generalised.

**Fixed.** `produce()` snapshots the seven at entry and rewinds to *that* on every
refusal path; `main()` no longer calls `restore_to_head` on refusal (which would
have re-introduced the defect by overwriting the rewind). `restore_to_head`
remains only where resetting to `HEAD` is the actual intent — `--restore`.
Pinned by `test_a_refusal_restores_an_operator_edit_rather_than_resetting_to_head`.

## O-D (medium, test) — the AC-4 and AC-6 tests did not exercise the failing paths

**Accepted in full.** The AC-4 tests only supplied a failure as the *final*
outcome of a mocked `converge`, so O-A passed every test. Both gaps are now
covered by the three tests named above.

---

## On `gemini: unavailable`

Its reply was cut off by the provider partway through analysing
`_branch_base_commit` and `deliver_stage`. The fragment reached no finding, so
nothing is being dropped. Recording it as `unavailable` rather than as agreement:
a review that did not finish is not a review that found nothing.
