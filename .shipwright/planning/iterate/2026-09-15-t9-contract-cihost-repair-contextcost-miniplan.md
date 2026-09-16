# Mini-Plan: t9 — AC-proving tests for FR-01.15 (cross-repo contract) + FR-01.17 (independent re-check on the code host) + FR-01.19 (recovery of a broken shared branch) + FR-01.20 (context-cost meter)

Campaign: `req3-05-test-backfill-mono`. Run-ID:
`iterate-2026-09-15-t9-contract-cihost-repair-contextcost`.
Branch: `iterate/campaign-req3-05-test-backfill-mono-t9`. **Final sub-iterate
of this 10-unit campaign (t0-t9).**

## Problem statement

31 ACs (`FR-01.15` AC01-AC08, `FR-01.17` AC01-AC07, `FR-01.19` AC01-AC10,
`FR-01.20` AC01-AC06) are listed `unbound` in
`shipwright_ac_coverage_baseline.json` at the start of this run — re-derived
directly from the file, matching the spec's stated count.

**Root list — pre-authorized vs. actually used (external plan review, openai,
high: the sub-iterate spec's own scope line names 2 roots, `shared/tests` and
`shared/scripts/tools/tests`; that is stale against the t0 seam survey's
per-unit root-count table, which pre-authorizes 4 for this unit — cited, not
re-decided, per that table's own row and its "campaign owner accepted,
2026-09-12" note):**

- **Pre-authorized ceiling (t0 seam survey, per-unit root-count table, t9
  row):** `shared/tests`, `shared/scripts/tests`, `shared/scripts/tools/tests`,
  `plugins/shipwright-iterate/tests` — 4 roots.
- **Actually used this run:** `shared/tests`, `shared/scripts/tests`,
  `shared/scripts/tools/tests` — 3 roots. `plugins/shipwright-iterate/tests`
  was never touched: every FR-01.19 (main-repair) AC that this unit bound
  turned out to have its real, already-passing proving test under
  `shared/tests` (`test_main_health*.py`, `test_main_attribution_workflows.py`,
  `test_repair_gate_bites.py`), not under the plugin's own test tree — so the
  4th pre-authorized root was headroom this unit did not need to spend.
- One `uv run pytest <root> --junitxml=...` invocation per one of the 3 roots
  actually used (ADR-044); no invocation was run against
  `plugins/shipwright-iterate/tests` and none is claimed.

## Approach

1. **FR-01.15** — cross-repo output contract. Real library seams
   (`contract_skeleton.py`, `contract_baseline.py`) already exist and are
   densely tested; the gap was AC-qualified tagging, not new tests, for
   AC01/AC04/AC07/AC08. AC05 needed one new test file
   (`test_contract_skeleton_weak_pins.py`, split out of
   `test_contract_skeleton.py` to hold the 300-line cap) covering
   `empty_array_paths` (previously untested) alongside the existing
   `null_only_paths` tests. AC08 ("the contract binds this side only")
   had no existing statement in either producer's SKILL.md — added one
   sentence to each (`plugins/shipwright-grade/skills/grade/SKILL.md`,
   `plugins/shipwright-adopt/skills/adopt/references/cross-repo-contract.md`)
   and a drift-pin test. **AC02/AC03/AC06 stay unbound per the seam
   survey's own Exception 2** ("do NOT tag... the library unit test alone
   does not prove the gate runs on a real diff") — the binding constraint on
   this unit's own spec ("cite the row t0 produced... rather than
   re-deciding the seam") is followed literally: `test_contract_gate_git.py`
   genuinely demonstrates git-ref immutability against a real throwaway
   repo, which reads as stronger evidence than Exception 2's "library unit
   test" framing anticipated, but Exception 2's own "Concrete machine
   outcome" section is explicit and reviewed twice (plan + code review) —
   overriding it unilaterally would be re-deciding the seam, not citing it.
2. **FR-01.17** — independent re-check on the code host. This is literally
   the Tier-3 PR-review gate this very run operates under. Six of seven ACs
   found real, already-passing, previously-untagged tests
   (`test_pr_review_fail_closed.py`, `test_pr_review_fork_trust.py`,
   `test_required_checks_drift.py` + `test_check_required_checks_cli.py`
   for the "raised as a tracked follow-up" half of AC06). AC01 ("tests,
   lint, security checks and the host's own code analysis all run again
   there") had no existing test asserting all four run on a pull request
   for THIS repository's own workflows (the sibling convention tests pin
   the templates Shipwright *scaffolds*, not this repo's own CI) — one new
   file (`test_ci_reruns_the_full_verification_on_pr.py`) added. **AC03
   stays unbound** (new Exception 10 in the seam survey): its "automatic,
   no ask" clause is real and tested, but "only the project owner can waive"
   is enforced by GitHub's own repository-permission ACL on who may apply a
   label — nothing in this codebase implements or narrows that, so the
   conjunctive AC's second clause has no in-repo seam.
3. **FR-01.19** — recovery of a broken shared branch. Dense, mature,
   previously-untagged test suite (`test_main_health*.py`,
   `test_main_attribution_workflows.py`, `test_repair_gate_bites.py`) proves
   all 8 ACs about main-repair's own decision logic (attribution,
   escalation, the claim/abandon race, the base-not-branch enforcement
   boundary, the bloat-crossing-on-merge visibility). **AC09/AC10 stay
   unbound** (Exception 11 in the seam survey): their TEXT reads as
   `/shipwright-grade` subject matter (network disclosure, grade-scope
   language) misplaced under this FR, but no test anywhere in the
   repository — under FR-01.19 or FR-01.18 alike — proves either AC's
   actual clause (verified by repo-wide grep for the actual language) —
   a `spec.md` authoring defect, not a seam this FR's own domain has
   anything to bind.
4. **FR-01.20** — context-cost meter. All 6 ACs bound across the three
   layers the survey's own per-FR note describes (hook capture / session
   fold / CLI summary): dedup-by-request-id and phase attribution
   (`test_context_cost_core.py`, split into
   `test_context_cost_core_phase_labels.py` to hold the 300-line cap),
   statusline running-total + on-demand phase breakdown (two new tests added
   to `test_context_cost_summary.py`: one proving `show` returns `by_phase`
   on demand, one end-to-end through the real `track_context_cost.py` Stop
   hook — added post-review, external code review, glm medium — proving the
   live per-session file actually contains phase buckets, not merely that
   `show` echoes a hand-authored one), readiness checks
   (`test_context_cost_readiness.py`), and the
   opt-in/default-toolcall dispatch (`test_context_pressure.py`, with one
   new CLI-level subprocess test added — `TestCLIDefaultSource` — since
   neither existing test class exercised `main()`'s actual `--source`
   dispatch between the two functions).
5. Regenerate `.shipwright/compliance/test-traceability.json` via
   `update_compliance.py --phase iterate` (wraps the `test_links` collector
   correctly — the collector script itself cannot run standalone via
   relative import), then `shipwright_ac_coverage_baseline.json` via
   `check_ac_coverage_ratchet.py --write`; leave both derived-file families
   uncommitted-but-present per t3-t8's established convention.

## Alternatives considered

- **Tagging FR-01.15 AC02/AC03/AC06 onto the existing library unit tests**,
  since `test_contract_gate_git.py` demonstrates real git-based immutability
  more convincingly than Exception 2's own framing assumed. Rejected: the
  binding constraint requires citing t0's row rather than re-deciding the
  seam, and Exception 2's "Concrete machine outcome" already went through
  two external-review rounds with an explicit instruction not to close these
  three via a library-only test. Overriding a twice-reviewed campaign
  decision from inside a single unit is not this unit's call.
- **Treating FR-01.17/AC03 as bound** on its "automatic, no ask" clause
  alone. Rejected per the same conjunctive-AC rule this campaign has applied
  throughout (Exceptions 2/4/9): a partially-provable clause does not make
  the whole AC provable, and the waiver-authority clause has no in-repo
  seam at all (it is GitHub's ACL, not this codebase's logic).
- **Inventing a main-repair-specific test for FR-01.19/AC09-AC10's literal
  text.** Rejected: the text reads as `/shipwright-grade` subject matter,
  but no test anywhere — under FR-01.19 or FR-01.18 — proves either AC's
  actual clause, so a test built around a spec typo would prove nothing
  real and misrepresent which FR's behavior it demonstrates.

## Result

24 of 31 ACs bound (FR-01.15: 4/8, FR-01.17: 6/7, FR-01.19: 8/10 bound with
AC09/AC10 explicitly recorded as exceptions, FR-01.20: 6/6). 7 stay unbound
with a concrete, evidenced, already-recorded reason each: FR-01.15
AC02/AC03/AC06 (seam survey Exception 2, pre-existing) and AC08 (seam survey
Exception 2 addendum, corrected 2026-09-15 after external plan review — see
below); FR-01.17 AC03 (seam survey Exception 10, new this run); FR-01.19
AC09/AC10 (seam survey Exception 11, new this run — spec-text duplication).

**AC08 correction (external plan review, glm medium + openai high, found
during this run's own review pass, corrected before commit):** this unit's
first pass bound `FR-01.15/AC08` to a documentation sentence added to both
producers' SKILL.md plus a drift-pin test, both authored in this same run.
Both external reviewers independently named this the same self-fulfilling-test
shape Exception 8 already rejects for its own drift-pin tests: the pin proves
the sentence persists, not that any machine behavior enforces the scope claim
it makes. The `@pytest.mark.covers("FR-01.15/AC08")` marker was removed; the
test and both doc sentences are kept, unmarked, as a real guard against the
sentence being silently deleted later. AC08 is recorded unbound under the
seam survey's Exception 2 addendum (dated 2026-09-15), alongside AC02/AC03/AC06
— four of this FR's eight ACs are residual-gate/documentation-only, not three.

`shipwright_ac_coverage_baseline.json` unbound_count: 69 -> 45 repo-wide
(one higher than this unit's own first-pass total of 44, reflecting the AC08
reversal above). This is the final unit of the campaign; all 10 sub-iterates
(t0-t9) are complete after this run.
