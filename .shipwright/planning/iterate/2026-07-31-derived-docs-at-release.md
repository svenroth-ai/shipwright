# Iterate: the compliance evidence documents ship at release (Weg B)

- **Run ID:** `iterate-2026-07-31-derived-docs-at-release`
- **Intent:** CHANGE
- **Complexity:** medium (`prior_source: history`, no risk flags)
- **Spec Impact:** NONE — no FR gains, loses or changes behaviour. The seven
  documents already exist and are already recomputed at release; this changes
  *where the recomputation lands* and *what the documents claim about
  themselves*.
- **Cards:** `trg-012db453` (Weg B) + `trg-d0e4592e` (the gate's remedy).
  Paired for scheduling only — see "Two subjects, one cycle" below.

---

## Problem

### A — the evidence on `main` is frozen and does not say so

PR #480 stopped iterate branches from committing eleven regenerated snapshots.
The reason was measured, not theoretical: a branch-local derivation reads the
*branch's* git history and an event log missing every concurrently-merging
branch, so `main`'s `change-history.md` over-counted commits by 11 and cited a
SHA `git merge-base --is-ancestor` proves was never on `main`. Freezing was the
right emergency move — frozen is not worse than wrong.

It was never the destination. A product whose selling point is auditability
cannot ship stale evidence, and the stale copies carry no marker saying they are
stale, so a reader cannot tell.

Three independent architecture reviews rejected the built alternative (Weg A: a
post-merge robot with a deploy key writing straight to protected `main`). The
key was measured working — commit `86a948ac`, `remote: Bypassed rule
violations` — so this is a judgement call, not an impossibility, and the
decision paper records it that way so it stays revisitable.

**Decided 2026-07-30 by the operator: Weg B.** The open question ("does anyone
read the evidence on `main` continuously between releases?") was answered *no*.
Full reasoning, in plain German:
`.shipwright/planning/iterate/2026-07-30-derived-snapshots-decision.md` on
branch `iterate/derived-snapshots-refresh`.

### B — the derived-snapshot gate sends the operator in a circle

`derived_snapshot_gate.py` blocks correctly, then prints a remedy that does
nothing on the very shape it was taught to catch:

```
git restore --source=HEAD~1 --staged [--worktree] -- <paths>   then amend
```

On a **merge HEAD** — the shape the gate now catches, the offender in an earlier
commit with an `ensure_current` merge on top — `HEAD~1` is the FIRST PARENT: the
branch's own pre-merge tip, i.e. precisely the commit carrying the offending
snapshot. The restore writes the offending content over itself, the amend
changes nothing the gate looks at, and the next run fails identically.

Nothing bad ships. This is purely about the operator looping.

---

## What was measured, so the scope is not guessed

**Regeneration just works for the tree-derived set — there is no backlog to
catch up.** Probed 2026-07-30 by regenerating all seven in a throwaway worktree
at `main` (`a3e625fc`) and diffing against what is committed. It is a pure
RECOMPUTATION, not incremental: one run reproduces the correct current state
from `shipwright_events.jsonl` + triage + git history, all of which already
ship. `test-evidence.md` moved 881 lines, which looks alarming and is not — new
rows are PREPENDED, so every index below shifts and the whole table diffs. The
`ok` markers were 40 added / 40 removed: balanced, no regression.

**The release phase already recomputes them.** `PHASE_REPORTS["changelog"]` in
`plugins/shipwright-compliance/scripts/tools/update_compliance.py` lists
`rtm, test_evidence, test_links, change_history, sbom, dashboard` — every
document in the set. It fires from `orchestrator update-step --step changelog
--status complete`, which the changelog skill runs in Step 8, *after* the
release commit in Step 6. So the fresh files land in the working tree and are
never staged. **This is an ordering defect, not a missing capability.**

**Three things the build must get right anyway** (scope, not backlog):

1. **`ci-security.json` is NOT tree-derived.** The parked branch classified it
   `DERIVES_FROM_CI_HISTORY`: `refresh_ci_security` reads the LATEST COMPLETED
   CI scan, not the repository. At release time that is fine in practice — a
   scan just ran on the release PR — but B must **state** the dependency rather
   than assume all seven behave alike. This is the parked iterate's H4 finding.
2. **`build_dashboard.md` and `session_handoff.md` are SESSION_SCOPED and stay
   OUT.** They embed a `run_id` for one specific run; `main` has none, so a
   refresh could only invent one. The set is **the compliance directory** and is
   pinned as such, so a later hand cannot widen it to "all eleven derived
   snapshots".
3. **`shipwright_test_results.json` is RUN_WRITTEN and is nobody's to
   regenerate** — `trg-ad29a709`, shipped as PR #502.

**The gate's secondary claim is narrower than filed — checked, not assumed.**
`trg-d0e4592e` also reports that for a path the branch never touched, the
printed command reverts mainline's version into the index. The offender list
comes from `_iterate_changed_paths`, which diffs `base..commit` where `base` is
the **narrowest** merge-base (`_branch_base_commit`). After an `ensure_current`
integrate that base *is* `origin/main`'s tip, so mainline's own changes are
already outside the range; before an integrate, mainline's later work is not in
`commit` at all. So the offender list is already branch-bounded in the primary
path, and the fallback (`_commit_changed_paths`) returns `None` on a merge HEAD
rather than a wrong list. **Only the remedy source needs fixing.** Recorded here
because "we checked and it was narrower" is a result, not a scope cut.

---

## Two subjects, one cycle

The two cards are built together for **scheduling only**. There is no technical
dependency and nobody should later infer one:

- **CHECKED AND FALSE:** that B would have to touch the derived-snapshot gate.
  The worry was that B's release-time check-in and its on-demand docs PR would
  commit the seven files and trip `check_no_derived_snapshots_committed`. They
  do not — that gate is reachable ONLY from `iterate_checks.py`'s F11 check
  list, and the changelog/release phase never invokes
  `verify_iterate_finalization`. A release commit and a docs-only PR both pass
  it without noticing it exists.
- **Why pair anyway:** a finalization cycle (F0–F11, three review stages,
  external review, PR, merge) costs hours regardless of diff size. B is four
  small build items; the remedy fix is ~30 lines plus tests.

They stay separable **by file**: B touches the refresh machinery, the changelog
and compliance skills, the stamp and the docs; the remedy fix touches
`derived_snapshot_gate.py` and its test only.

---

## Approach

### Reused from the parked Weg-A branch

The decision paper lists what survives the choice of path, because it is about
*computing correctly* rather than *who may write*. Ported, rescoped, and kept:

| Piece | Why it stays |
|---|---|
| Explicit per-path CLASSIFICATION + the test that a new unclassified derived path FAILS | Eligibility is declared, never inferred from a file extension |
| Fixpoint regeneration (converge) | `update_compliance` collects once then renders in list order, so the RTM reads the `test-traceability.json` the same pass later overwrites — pass 1 ≠ pass 2, pass 2 == pass 3 (measured) |
| Failed-pass detection (a closed SUCCESS vocabulary) | `_update_compliance` swallows non-zero exits, its own timeout and every exception and returns `[]`; without propagation an all-error run reads as a clean fixpoint and ships frozen documents while reporting green |
| Content floor | `collect_git_history` returns `[]` on its 30s timeout, rendering a well-formed document with no rows — which converges perfectly and would replace "wrong by 11 commits" with "zero commits" |
| Take-the-set commit construction | "Nothing else can ride along" holds by construction rather than by a `git status` check that fails open |

### Discarded from the parked branch

`refresh-derived-snapshots.yml`, the deploy key + secret + ruleset bypass entry,
the debounce, the loop guard (`Refresh-Base` trailer, `should_skip`,
`is_own_commit`), the `paths-ignore` entries in `ci.yml`/`codeql.yml`,
`refresh_derived_failure.py` (the AC-7 failure card), and the workflow-delivery
tests. Every one of them existed only to survive writing directly to `main`.

**Not discarded:** `test_workflow_token_permissions.py` is older than that
effort and enforces least-privilege across *all* workflows.

### The four build items

**1 — the release ships the seven files.** A new step in the changelog skill,
*before* the release commit: regenerate to a fixpoint, verify, and stage
exactly the seven by explicit pathspec. They then ride the `chore(release)`
commit into the release PR a human already opens and reviews.

**2 — a named step in `/shipwright-compliance` opens a docs-only PR.** Same
producer, different delivery: a branch off freshly-fetched `origin/main`,
take-the-set so nothing else rides along, `gh pr create`. Same checks and same
visibility as any other change. The operator's own credential; no bot, no key,
no exception to the branch-protection rule.

**3 — the stamp names a fixed point.** The `Source-State:` banner every
evidence document already carries gains two tokens: `base=<sha12>` (the commit
the inputs were read from) and `release=<tag>` (the release it shipped with).
Both absent by default, so an ordinary in-run regeneration renders exactly as
today and stays deterministic. For audit evidence a fixed point is the better
claim than a moving one.

**4 — docs.** `docs/guide.md` gains what is current, what is not, and how to
refresh it. `docs/hooks-and-pipeline.md`'s artifact-write matrix gains the
release phase's new write and the new tool.

### The gate remedy (item 5, separable)

Resolve the restore source with `_branch_base_commit` — the state before the
branch touched anything — instead of `HEAD~1`. When no base resolves, print an
instruction that does not name a commit at all rather than one that names the
wrong one.

---

## Acceptance Criteria

- **AC-1** The refresh set is exactly the compliance directory — the five
  compliance MDs, `test-traceability.json`, `ci-security.json`. Declared, not
  derived from a path shape. A `DERIVED_SNAPSHOTS` member with no classification
  entry fails a test.
- **AC-2** `build_dashboard.md`, `session_handoff.md` (SESSION_SCOPED),
  `shipwright_test_results.json` (RUN_WRITTEN) and `triage_inbox.md` (tree-derived
  but outside the compliance directory) are each excluded **by name with a
  reason**, so the exclusion cannot read as an oversight.
- **AC-3** Regeneration runs to a fixpoint and FAILS loudly when it cannot reach
  one within the pass cap.
- **AC-4** A pass in which a producer leg errored is reported as a failure, not
  as "nothing changed". A closed success vocabulary: an unknown outcome string
  is a failure until somebody adds it on purpose.
- **AC-5** A regenerated document that lost material content versus `HEAD`
  blocks the refresh. Two floors: never empty when `HEAD` had content, and never
  below half its committed size. `--allow-shrink` overrides the ratio floor and
  **records** that it did, naming the paths — a legitimate large removal can
  halve a document, so the override exists; a silent one would not.
- **AC-6** `ci-security.json`'s dependency on CI history is **stated** in the
  tool's output and its classification. When it cannot be refreshed the frozen
  copy stands and the result says so. The tool additionally compares the
  committed `scan_date` against the base commit's date and reports
  `ci_security.stale` when the scan predates the code it ships beside. None of
  this ever fails the run — a release is not blocked on a scan that has not
  landed.
- **AC-7** The release path stages exactly the seven paths, reports which of them
  actually differed from `HEAD`, and prints the **explicit pathspec** the release
  commit must use. The commit boundary is the pathspec, not the index: `git
  commit -- CHANGELOG.md <the seven>` contains exactly those paths whatever else
  happens to be staged.
- **AC-8** The on-demand path produces a commit containing **only** the seven
  paths, by construction (restore-to-base → write-back → commit by pathspec),
  and opens a PR against the default branch.
- **AC-8b** Before pushing, the on-demand path re-reads `origin`'s
  default-branch SHA and aborts when it moved since the base was captured.
  Recomputing is cheap; shipping a knowingly-stale refresh is pointless.
- **AC-9** The `Source-State:` banner round-trips `base=` and `release=`;
  both absent renders byte-identically to today. Both values are validated
  before they reach a banner or a ref name — `base` as 7–40 hex, `release` as a
  single whitespace-free token — and an invalid value is dropped, never
  sanitised into something that looks legitimate.
- **AC-9b** `release=` is emitted **only** by the release delivery. `--pr` and
  `--release` are mutually exclusive and the tool refuses the combination rather
  than choosing for the operator: a documents-only branch off `origin/main` did
  not ship with any release, and stamping the latest tag would claim it did.
  The release version is **passed in** by the changelog skill, never resolved
  from git — at the moment it is needed the tag does not exist yet.
- **AC-13** After the release commit, the changelog skill's phase-completion call
  (`orchestrator update-step --step changelog --status complete`) regenerates the
  same seven documents a second time, unstamped and at a different commit. The
  release flow restores them to `HEAD` afterwards, so the committed stamped
  copies win and the worktree does not end the release permanently dirty.
- **AC-10** `docs/guide.md` and `docs/hooks-and-pipeline.md` state what is
  current, what is not, and how to refresh it.
- **AC-11** (gate) On a merge HEAD, the remedy the gate prints resolves to the
  branch's merge-base — not `HEAD~1` — and following it actually clears the gate.
- **AC-12** (gate) With no resolvable base, the gate prints no `--source` at all
  rather than a wrong one.

## Spec Impact justification

`spec_impact: none`. No functional requirement is added, changed or removed.
The seven documents, their content and their producers are unchanged; what
changes is which commit carries them, and two extra tokens in a header line.
`affected_frs` names the requirements whose *evidence* now ships fresh, which is
legal alongside `none` and is why this justification is required.

## Affected Boundaries

- **Subprocess boundary** — `refresh_compliance_docs` → `update_compliance.py`
  via `regenerate_tracked_snapshots`. The stamp values cross it as
  `SHIPWRIGHT_COMPLIANCE_*` environment variables because the generator is not
  ours to re-signature (threading a CLI flag would mean editing
  `resolve_churn_conflicts.py`, which is `cross_component` machinery).
- **Git boundary** — index staging, branch creation, commit by pathspec, push.
- **GitHub boundary** — `gh pr create` under the operator's own credential.
- **Text boundary** — the `Source-State:` banner: render → parse round-trip.

## Self-Review

1. **Spec compliance.** All 13 ACs implemented and tested (ledger below). Two
   claims in the plan turned out narrower than filed and are recorded as results
   rather than quietly dropped: the gate's secondary offender-list claim (already
   handled by the merge-base range) and the stamp's delivery mechanism (moved off
   an env-var subprocess boundary onto the deliverer).
2. **Tests.** 24 new tests across 6 modules plus 3 amended contract tests. TDD
   held for the decisions module; the delivery tests were written against
   observable artifacts (the git index, the commit's path set) rather than return
   values — which is the only reason HIGH-1 was catchable.
3. **Error handling.** Every refusal is explicit and returns a status the caller
   must branch on; none is swallowed. `produce` restores the tree on refusal so a
   rejected regeneration cannot be picked up by a later `git add`. `deliver_pr`
   restores the operator's branch in a `finally`, and every failure path after the
   commit says where the work is instead of discarding it. `converge` rewinds the
   producer inputs in a `finally`, so a raising generator cannot leave its
   throwaway appends in the operator's event log.
4. **Security.** No new credential, no workflow, nothing under `.github/`. Both
   deliveries go through a reviewed PR; the on-demand one uses the operator's own
   `gh` login. Every `git`/`gh` call is an argv list, never a shell string. Values
   reaching a ref name or a banner are validated first (`safe_commit` 7–40 hex,
   `safe_run_id` single token) and dropped rather than sanitised on failure —
   `test_a_release_value_cannot_forge_a_commit_or_status_token` pins that a
   release value cannot forge a second banner token. `capture` skips symlinks
   rather than reading a target's bytes onto a public branch.
5. **Performance.** Bounded: at most 4 regeneration passes, and the strict floor
   re-run only happens under `--allow-shrink`. No new network call on the release
   path.
6. **Conventions.** `lib/` ⟷ `tools/` split as the churn tooling already does;
   `uv run` entry points; Conventional Commits; docs updated per CLAUDE.md's rules
   for `guide.md` and `hooks-and-pipeline.md`. **Three known deviations, disclosed
   rather than hidden:** `source_state.py` at 307 and
   `compliance_refresh_produce.py` at ~320 exceed the 300-LOC guideline, and the
   changelog `SKILL.md` at ~435 exceeds its 400-line runtime-prompt limit. I
   trimmed each twice; further cuts would have removed the reasoning or the
   operator-actionable guidance rather than fat. None carries a bloat-baseline
   entry, so nothing ratchets — these are new crossings for the Group H audit, and
   a reviewer should feel free to overrule the call.
7. **Affected Boundaries.** Listed below and each one probed, not asserted.

## Confidence Calibration

- **Boundaries touched:** git index/worktree (staging, branch creation, commit by
  pathspec, push), GitHub via `gh pr create` under the operator's own login, the
  `Source-State:` text banner (render → parse round-trip), and the subprocess
  boundary into `update_compliance.py` via `regenerate_tracked_snapshots`. The
  environment-variable boundary the plan proposed for the stamp was **removed**:
  the stamp is applied by the deliverer to the captured bytes, so no value crosses
  into the generator subprocess at all.

- **Empirical probes run:**
  - *Does the release actually recompute all seven today?* Read
    `PHASE_REPORTS["changelog"]` in `update_compliance.py` — it lists rtm,
    test_evidence, test_links, change_history, sbom, dashboard. Confirmed: this is
    an ordering defect, not a missing capability.
  - *Is the gate's secondary claim (mainline paths named as offenders) real?*
    Traced `_iterate_changed_paths` → `_branch_base_commit`: after an integrate the
    base IS `origin/main`'s tip, so mainline's changes are outside `base..commit`;
    before one they are not in `commit` at all. **Narrower than filed** — only the
    remedy source needed fixing. Recorded rather than silently scoped out.
  - *Does the fixed remedy actually clear the gate?* Not inspected — **executed**.
    `test_following_the_printed_remedy_clears_the_gate_on_a_merge_head` builds the
    merge-HEAD shape, runs the gate, extracts the printed `--source`, runs that
    exact `git restore` + `--amend`, and re-runs the gate. Red → green.
  - *Do the stamped bytes reach the release commit?* Not asserted on the return
    value — read back out of the **git index** (`git show :<path>`) after a real
    `main(--stage --release …)` run. This probe is why HIGH-1 was found at all:
    the first implementation reported `stamped: [...]` while staging unstamped
    bytes, and every test that trusted the return value passed.
  - *Does the skill's literal pathspec match the registry?* Parsed out of
    `SKILL.md` and compared set-wise; the reader returns 8 paths, verified
    non-vacuous by printing them.
  - *Does the producer discard uncommitted work?* Wrote an operator append into
    `shipwright_events.jsonl`, ran `converge` with a producer that appends its own
    row, and asserted the operator's row survived while the run's did not —
    including on a raising producer.

- **Test Completeness Ledger:** 32 behaviours, **0 testable-but-untested** (one testable gap is named explicitly below and becomes a follow-up card, which is a work item rather than a spec note).

| # | Behaviour | Category | Disposition | Evidence |
|---|---|---|---|---|
| 1 | Every derived snapshot carries a classification | unit | tested | `test_compliance_refresh.py::test_every_derived_snapshot_carries_a_classification` |
| 2 | Refresh set == the compliance directory, exactly seven | unit | tested | `::test_refresh_set_is_exactly_the_compliance_directory`, `::test_the_refresh_set_is_the_seven` |
| 3 | Every exclusion named with a reason; no session/run-written path can enter | unit | tested | `::test_every_non_refreshed_snapshot_is_excluded_by_name_with_a_reason`, `::test_no_session_scoped_or_run_written_path_can_reach_the_refresh_set` |
| 4 | Regeneration reaches a fixpoint | integration | tested | `test_compliance_refresh_produce.py::test_a_stable_producer_converges_on_the_second_pass` |
| 5 | A producer that never settles is refused | integration | tested | `::test_a_producer_that_never_settles_fails_rather_than_committing_a_pass` |
| 6 | `ci-security.json` is outside the fixpoint claim | unit | tested | `::test_convergence_ignores_a_moving_ci_security`, `test_compliance_refresh.py::test_ci_security_is_outside_the_fixpoint_claim` |
| 7 | A failed pass ≠ a pass that found nothing (closed vocabulary) | unit | tested | `::test_an_all_error_pass_is_reported_as_a_failure_not_a_fixpoint`, `::test_one_unknown_outcome_word_is_enough_to_refuse` |
| 8 | Content floor: emptied document blocks | unit | tested | `::test_an_emptied_document_blocks_the_refresh` |
| 9 | Content floor: ratio blocks; `--allow-shrink` waives it and **names the paths** | unit | tested | `::test_allow_shrink_waives_the_ratio_floor_and_records_that_it_did`, `::test_allow_shrink_records_an_empty_waiver_when_nothing_shrank` |
| 10 | `--allow-shrink` never waives the empty floor | unit | tested | `::test_allow_shrink_never_waives_an_emptied_document` |
| 11 | A path missing from the payload is blocked, not skipped | unit | tested | `::test_a_path_missing_from_the_payload_is_blocked_not_skipped` |
| 12 | `capture` skips a symlink instead of reading through it | unit | tested | `::test_capture_skips_a_symlink_rather_than_reading_through_it` (CI hard-fails the skip) |
| 13 | `ci-security` reports class, scan, staleness; unknown ≠ fresh; never fails the run | unit | tested | 5 tests incl. `::test_an_unresolvable_base_reports_freshness_as_unknown_not_fresh`, `::test_ci_security_never_fails_the_run` |
| 14 | Producer inputs are rewound to the operator's state, not to `HEAD`; an append-only log that changed is never overwritten; a rewritten config always is | unit (see note) | tested | `::test_uncommitted_appends_to_the_event_log_survive_the_run`, `::test_the_inputs_are_rewound_even_when_a_pass_raises` |
| 15 | Banner round-trips `base=`/`release=`; absent renders byte-identically | unit | tested | `test_source_state_fixed_point.py` (12 tests) |
| 16 | Stamp applied to markdown only; `.json` and banner-less files untouched | unit | tested | `test_compliance_refresh_stamp.py` (5 tests) |
| 17 | **The STAGED bytes are the stamped ones** (read from the git index) | integration | tested | `test_refresh_compliance_docs.py::test_the_staged_bytes_are_the_STAMPED_ones`, `::test_an_on_demand_stage_carries_a_base_but_no_release` |
| 18 | `release=` only on a release delivery; `--pr`+`--release` refused; version never read from git | integration | tested | `::test_pr_and_release_together_are_refused`, `::test_the_release_version_is_never_resolved_from_git` |
| 19 | Release staging reports only what differed; the printed pathspec bounds the commit | integration | tested | `::test_stage_reports_only_what_actually_differed`, `::test_the_release_commit_pathspec_excludes_unrelated_staged_work` |
| 20 | The skill's literal pathspec cannot drift from the registry | unit | tested | `test_release_pathspec_doc_sync.py` (both directions + no-directory-pathspec) |
| 21 | The docs-only PR carries **only** the seven; returns to the starting branch; noop when unchanged; aborts on a moved base; preflight refuses a dirty or behind checkout | integration | tested | `test_refresh_compliance_docs.py` (7 tests) |
| 22 | Gate remedy: following the printed command clears the gate on a merge HEAD; no base → no `--source`; the finding survives; run-written offenders never get `--worktree`; a commit already on the trunk gets words, not `--source=<itself>` | integration | tested | `test_derived_snapshot_gate_remedy.py` |
| 23 | A failure in ANY pass fails the run, not only the last one | unit | tested | `::test_a_failure_in_an_EARLIER_pass_still_fails_the_run` |
| 24 | `ci-security.json` never fails the run; a tree-derived failure beside it still does | unit | tested | `::test_a_ci_security_producer_failure_never_fails_the_run`, `::test_a_tree_derived_failure_alongside_ci_security_still_refuses` |
| 25 | A failed `git add` is a refusal, never "nothing to do"; `[]` and `None` come from different causes | unit | tested | `::test_a_failed_git_add_is_not_reported_as_nothing_to_do`, `::test_staged_difference_distinguishes_clean_from_blind` |
| 26 | A release value cannot forge a second banner line through the substitution, and an unknown escape does not raise | unit | tested | `test_compliance_refresh_stamp.py` (2 tests) |
| 27 | The docs-only commit carries the trailer the staleness audit recognises | unit | tested | `::test_the_docs_commit_carries_the_trailer_the_staleness_audit_recognises` |
| 28 | A refusal restores an operator's edit rather than resetting to `HEAD` | unit | tested | `::test_a_refusal_restores_an_operator_edit_rather_than_resetting_to_head` |
| 29 | **The COMMIT carries the stamp** — read from `git show <sha>:<rel>`, not the index | integration | tested |
| 30 | A concurrent append to an append-only input is never destroyed, and the path is reported to the operator | unit | tested | `::test_a_CONCURRENT_append_during_a_pass_is_never_destroyed`, `::test_a_left_alone_input_reaches_the_operator` |
| 31 | A rewritten producer config IS rewound (append-only handling is per path) | unit | tested | `::test_a_rewritten_producer_config_IS_rewound` |
| 32 | `restore_to_head` asks whether `HEAD` carries a path rather than inferring it from a failed checkout | unit | tested | `test_refresh_compliance_docs.py::test_restore_mode_needs_no_producer_and_reports_what_it_moved` (asserts the file still exists) | `::test_verify_commit_reads_the_COMMIT_and_catches_an_unstamped_one`, `::test_verify_commit_passes_on_a_commit_that_really_carries_the_stamp` |

  **One behaviour is testable and NOT tested, and is named rather than hidden:**
  the real `regenerate_tracked_snapshots` → `_update_compliance` producer is
  driven nowhere in this diff — every refusal, rewind and floor test injects
  `regenerate` or stubs `converge`. Stage 3 pointed out that this is precisely
  why D6 (the compliance config never rewinding) was invisible, and it is why row
  14 is relabelled `unit` rather than `integration`. Driving the real producer
  needs a fixture project with a full `.shipwright/` tree plus the compliance
  plugin on `sys.path`; that is a real gap, deferred deliberately rather than
  claimed as covered. **This is the one "could-test-but-didn't" in the run, and
  the disposition is that it becomes a follow-up card, not a spec note.**

  Two behaviours are **untestable** and named as such rather than left implicit:
  - The `gh pr create` call itself — `requires-external-nondeterministic-service`.
    Everything up to and including the commit is tested; the one call that reaches
    GitHub is substituted through `_gh_pr_create`, which exists precisely so a test
    can replace that call and nothing else (patching `subprocess.run` wholesale
    silenced every `git` call too, and a delivery test passed while proving
    nothing — found and fixed during the build).
  - The prose in `docs/guide.md`, `hooks-and-pipeline.md` and the two SKILL.md
    files — `requires-manual-visual-judgment`. The one machine-checkable claim in
    that prose (the commit pathspec) is covered by row 20 rather than left to it.

- **Confidence-pattern check:**
  - *Asymptote (depth).* The load-bearing claims are proven by execution, not by
    inspection: the gate remedy is **run**, the stamp is read back out of the
    **index**, "nothing else rides along" is tested by planting a stray file and a
    triage append and proving neither lands. Where a test could have passed
    vacuously I checked it explicitly — the pathspec reader was printed (8 paths),
    and the symlink skip hard-fails in CI.
  - *Coverage (breadth).* All 13 ACs map to at least one test (table above). Both
    deliveries are covered, all four refusal statuses are covered, and both
    directions of the two registry-drift guards are covered.
  - *Integration composition.* `cross_component` does **not** fire: no file in the
    diff matches `CROSS_COMPONENT_FILE_PATTERNS` (`integrate_main`,
    `ensure_current`, `resolve_churn_conflicts`, `churn_merge`, `events_log`,
    `hooks.json`, `hooks/*.py`, `verify_phase`, `get_phase_context`, campaign
    drain). `regenerate_tracked_snapshots` is *called* but not edited — a
    deliberate constraint recorded in the mini-plan's Risk section. Rows 4, 5, 14,
    17, 21 and 22 are nonetheless real-scenario `integration` behaviours that
    compose the producer, git and the gate against a live repository.
  - *Where I was wrong — three times, and the third is the useful one.*
    Stage 1 rejected the first implementation on four counts; HIGH-1 (the stamp
    never reaching the release path) was the change's headline deliverable,
    silently absent, while the run reported success. Stage 3 then found the SAME
    shape one step downstream: `git commit -- <pathspec>` records the WORKTREE,
    so reading the index — the lesson I had just learned — still proved nothing
    about the commit (row 29 now reads `git show <sha>:<rel>`). And my fix for a
    Stage-2 finding was backwards: an append-only prefix guard passes exactly
    when a concurrent append happened, and fires only on the case that was never
    the concern. Each layer caught a class the layer before it could not: the
    external review found contract gaps, Stage 2 found fail-open paths, Stage 3
    found fixes that did not fix what they claimed.
