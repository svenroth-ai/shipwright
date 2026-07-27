# Iterate: name the blocker instead of reporting a weaker signal

- **Run ID:** iterate-2026-07-27-name-the-blocker
- **Date:** 2026-07-27
- **Type:** change
- **Complexity:** medium
- **Branch:** iterate/name-the-blocker
- **Spec Impact:** MODIFY — FR-01.11, FR-01.03
- **Observed during:** iterate-2026-07-27-f0-race-triage (PR #439)

## Problem

Four checks in the finalization / delivery path already hold — or can obtain in
one query — the information needed to name *why* something is not proceeding.
Each reports a weaker signal instead:

1. **`watch_pr_delivery.py` says "timed out" where it could say "blocked".**
   PR #439 sat green for ~25 minutes: all 10 check-runs successful, PR Review
   successful, auto-merge armed. The watcher returned
   `{"status":"pending","timed_out":true}` three times. The real cause was one
   unresolved review thread, which blocks auto-merge on its own. Neither the
   check rollup nor the watcher mentions threads — and the payload the watcher
   *already fetches* carries `mergeStateStatus`, which it never reads.

2. **The `session_handoff.md` freshness check keys on filesystem mtime.** It
   fires on any run that waits longer than ~10 minutes on CI — structurally,
   not on a real defect. It also contradicts a decision this repo already
   recorded (iterate-2026-06-28-drop-timestamp-drift, now the standing comment
   at `shared/scripts/hooks/check_drift.py:10-16`): filesystem mtime is not a
   content-staleness signal in a git repo, because checkout, branch-switch and
   worktree creation all reset it. A warning operators learn to ignore is worse
   than no warning.

3. **Cross-layer coverage reports "could-not-determine" for the *encouraged*
   authoring pattern.** `shared/fr-authoring.md` §3 says folding is the common
   case: append an acceptance criterion to an existing requirement rather than
   mint a new row. `behavior_changed_keys` resolves behaviour change from FR
   **row** fields only (title, required_layers), so a correctly folded change
   leaves the row untouched and always lands in "no FR-row-level behaviour
   change was determinable". The pattern the framework recommends is the one
   pattern its gate cannot see.

   There is a second, quieter half of the same defect: when *some other* FR's
   row did change, `could_not_determine` is `False` and the AC-only-changed FR
   is dropped **silently** — not even a WARN.

4. **`external_review.py` reports a leg `success` when the reply is not a
   review.** On the run above, the Gemini leg returned an unfinished internal
   monologue while the transport reported success; only downstream human
   parsing exposed it as partial. Same class: success reported, nothing
   delivered.

## Scope decision for (3) — taken on evidence, not guessed

The brief flagged (3) as highest risk because it touches traceability gate
semantics, where the manifest/schema contracts are deliberately frozen. Read
before scoping:

- `plugins/shipwright-compliance/scripts/lib/traceability_schema.json` — v3,
  `additionalProperties: false` at **both** root and requirement level, and the
  description pins "Requirement INNER fields are unchanged from v2".
- The committed `test-traceability.json` is in `CHURN_ALLOWLIST`; a per-FR
  field addition would rewrite every requirement node on every regeneration.

**Finding: no schema change is required.** Each requirement node already
carries `spec_path`, and `_layer_coverage_regen._merge_base` already resolves
the base SHA. The acceptance criteria can therefore be read directly out of git
(`git show <sha>:<spec_path>`) at gate time. The manifest is not touched, the
committed artifact does not churn, and the frozen contract is untouched.

**Finding: the blocking posture does not change in this repo.** Every FR in
`.shipwright/planning/01-adopted/spec.md` carries `required_layers_source:
inferred_legacy` (verified against the committed manifest, all 18 rows), so a
resolved gap routes to ADVISORY, never HARD. Resolving could-not-determine
turns an unnamed WARN into a *named* WARN here; in a post-rollout repo with
`explicit` layers it would correctly go HARD, which is the intended semantics.

Item (3) therefore stays in this iterate. It is not its own piece of work.

## Non-goals (named so they are not silently swept in)

- The `classify_complexity` `touches_auth` prose false positive (the literal
  "session" in "session_handoff" matching an auth pattern). Over-flagging is
  the fail-safe direction and the diff-driven `risk_detectors` predicates are
  authoritative; an override plus a `degraded[]` line is the whole cost.
- Whether the code / doubt subagent review passes should run in autonomous
  iterates. That is an operator policy decision, not a defect.
- **The C3 twin.** `verifiers/common.py:382 check_c3_session_handoff_fresh_after_phase`
  has the identical mtime defect and is called by six phase verifiers. It is
  *not* fixed here: it is phase-scoped, has no `run_id` to key on, and its
  docstring records that session_handoff carries no per-phase marker — so a
  content key for it has to be designed, not ported. Filed as a tracked
  follow-up rather than guessed at.
- Tagging the new tests `@FR-01.11` to turn the resulting advisory WARN green.
  That belongs to the pending plugin-FR-tag backfill, not here.

## Affected Boundaries

| Boundary | Direction | Note |
|---|---|---|
| `gh pr view --json` payload | consume | existing; `mergeStateStatus` newly read |
| `gh api graphql` reviewThreads | consume | **new** external JSON shape |
| `gh api repos/…/rules/branches/<b>` | consume | **new** external JSON shape |
| `session_handoff.md` canon frontmatter | consume | producer is `generate_session_handoff.py`; the stop hook already consumes it |
| `spec.md` acceptance-criteria sections | consume | **new** parse surface, read via `git show` |
| OpenAI / OpenRouter / Gemini response objects | consume | `finish_reason` newly read |

## Acceptance Criteria

- **(A) Named blockers instead of a bare timeout.** When a pull request stays
  open with no failing check, the delivery watcher reports the reasons it is
  not merging — review conversations still unresolved, required checks that
  have not reported at all, and the code host's own "blocked" verdict — each
  named, instead of only saying it waited long enough. When it genuinely cannot
  tell, it says the blockers are unknown rather than implying there are none.
- **(B) Terminal verdicts are unchanged.** Adding blocker detail does not turn
  a merged, closed or failing pull request into a different verdict, and does
  not turn a pending one into "done". A blocker probe that fails leaves the
  watcher working exactly as before.
- **(C) Handoff freshness is judged by content.** The finalization check passes
  when the handoff names the run currently finishing, and fails when it names a
  different run or none — however long the run took. How recently the file was
  written is no longer consulted anywhere in that check.
- **(D) A folded acceptance criterion is seen.** A change that appends an
  acceptance criterion to an existing requirement — the pattern
  `shared/fr-authoring.md` §3 recommends — is resolved to that named
  requirement and checked at the layers that requirement requires, instead of
  being reported as undeterminable. This holds whether or not some other
  requirement's row also changed in the same change.
- **(E) Undecidable stays visibly undecidable.** A specification edit that
  touches no requirement's row and no requirement's acceptance criteria is
  still reported as could-not-determine for a human to adjudicate. It is never
  silently passed, and the reason it could not be decided is stated.
- **(F) A reply that is not a review is not a success.** An external review leg
  whose answer is empty, or which the provider itself reports as cut off, is
  recorded as degraded with the reason given, not as a successful review. When
  every leg degrades, the run fails loudly as it already does today.

## Confidence Calibration

- **Boundaries touched:** the six in Affected Boundaries above — three of them
  new consume-side external shapes (GraphQL review threads, the branch-rules
  REST payload, per-provider `finish_reason`), plus one new parse surface
  (acceptance-criteria sections read via `git show`).

- **Empirical probes run** — five, each against the real thing, and three of
  them changed the code:

  | Probe | Finding |
  |---|---|
  | `gh api graphql … reviewThreads` on PR #439 | Readable with the current token. `totalCount: 1`, now `isResolved: true` — **the exact thread that blocked the PR**. Confirms the data was one query away. |
  | `gh api repos/…/rules/branches/main` | Readable **without admin**; returns all six required contexts. `baseRef.branchProtectionRule` via GraphQL returned `null`, so the REST rules endpoint — not branch protection — is the usable source. |
  | Same endpoint against a branch with no ruleset | **Changed the code.** Returns `[]`, indistinguishable from "no checks required". A repo on classic branch protection would have been reported as "nothing required is missing". Empty is now `unknown`. |
  | `criteria_digests` over this repo's real `spec.md`, base commit vs working tree | Parsed all 18 requirements at both commits and named exactly the two this change folded into — `FR-01.03`, `FR-01.11` — and no others. On `main` today this same change reports could-not-determine. |
  | `external_review.py --mode code` on this iterate's own diff | **Caught one live.** The Gemini leg returned 767 chars with `finish_reason=length`; a second run returned empty. Both are now `degraded` with the reason. Under the old code both were `success`. |

  A sixth probe was a process failure worth recording: the first code review ran
  against `git diff --cached origin/main`, but `origin/main` had moved three PRs
  ahead of this branch's base, so the diff showed **other people's merged work as
  deletions**. Both reviewers duly reported high-severity "regressions" in files
  this change never touches. Rebuilt against the merge-base (`ce149b07`) and
  re-reviewed. A review of the wrong diff is worse than no review, because it
  arrives with the full authority of a review.

- **Test Completeness Ledger** — 18 behaviours, every one `tested`; zero
  testable-but-untested. Machine-readable copy at F5 in
  `shipwright_test_results.json.iterate_latest.test_completeness`.

  | # | Behaviour | Disposition | Evidence |
  |---|---|---|---|
  | 1 | A pending verdict carries named blockers | tested | `test_watch_pr_delivery::test_pending_timeout_carries_named_blockers` |
  | 2 | The probe is told which PR/branch, from the payload's own url | tested | `…::test_the_probe_is_told_which_pr_and_branch_to_look_at` |
  | 3 | Terminal verdicts unchanged and never probed | tested | `…::test_terminal_verdicts_are_not_probed_and_not_changed` |
  | 4 | A probe that raises never costs the verdict | tested | `…::test_a_probe_that_raises_never_costs_the_verdict`, `test_pr_blockers::test_probe_turns_a_fetch_failure_into_an_unknown_source` |
  | 5 | The operator-facing line names the cause | tested | `…::test_pending_report_names_the_cause_in_plain_words` (+2) |
  | 6 | Unresolved threads are a named cause | tested | `test_pr_blockers::test_an_unresolved_thread_is_a_named_cause` |
  | 7 | A truncated thread page never claims "none unresolved" | tested | `…::test_a_truncated_page_with_nothing_unresolved_is_unknown_not_clean` (+1) |
  | 8 | A required check that never reported is named, and distinguished from one still running | tested | `…::test_a_required_check_absent_from_the_rollup_is_named` (+1) |
  | 9 | Contexts are collected from every matching ruleset | tested | `…::test_contexts_from_every_ruleset_rule_are_collected` |
  | 10 | Unreadable / empty rules are `unknown`, never "nothing missing" | tested | `…::test_unreadable_rules_is_unknown_never_no_missing_checks`, `…::test_an_empty_rules_list_is_unknown_not_nothing_required` |
  | 11 | An unknown host merge state is an unknown source | tested | `…::test_an_unknown_host_merge_state_is_an_unknown_source` (+2) |
  | 12 | `blocking` asserted only when the host says BLOCKED | tested | `…::test_causes_are_reported_without_asserting_blocking_when_merge_state_disagrees` |
  | 13 | Handoff freshness passes on age, fails on the wrong run, and never reads mtime | tested | `test_handoff_freshness` (13 tests, incl. `test_the_check_never_consults_mtime`) |
  | 14 | Only the `Current Iterate Progress` marker satisfies the fallback | tested | `…::test_last_iterate_run_id_does_not_satisfy_the_check` (+2) |
  | 15 | Writer → Stop hook → verifier agree on one canon marker, incl. the hook's production entry point from an unrelated cwd | tested (**integration**) | `test_handoff_freshness_composition` (5 tests) |
  | 16 | A folded criterion resolves to its named requirement, incl. alongside a row change | tested | `test_layer_coverage_verdict::test_a_folded_criterion_resolves_to_its_named_requirement` (+1) |
  | 17 | Undecidable stays visibly undecidable; a pure refactor stays green | tested | `…::test_undecidable_stays_undecidable`, `…::test_a_pure_refactor_is_still_green` |
  | 18 | An unreadable spec blocks at medium+ instead of reading as unchanged | tested | `…::test_an_unreadable_spec_blocks_a_medium_iterate_rather_than_reading_as_unchanged` (+1) |

- **Confidence-pattern check:**
  - *Depth (asymptote).* Each site is exercised at its own seam: pure functions
    directly, the two gh shells through injected payloads, and the live API for
    the shapes themselves. The probes stopped returning new information after the
    empty-ruleset finding — the next three all confirmed rather than corrected.
  - *Breadth (coverage).* The four sites and their failure modes are enumerated
    in the ledger. The recurring axis across all of them is *unknown vs clean*,
    and every source has an explicit test that it degrades to "unknown" rather
    than to "fine".
  - *Integration composition.* Required: this change edits
    `hooks/generate_handoff_on_stop.py`, which the F11 verifier recomputes as
    `cross_component` machinery. `test_handoff_freshness_composition.py` proves
    the writer, the Stop hook and the verifier agree on one canon-frontmatter
    format on disk — three components that each passed their own suite while
    nothing checked that they meant the same thing.

## Self-Review

1. **Spec compliance.** Six acceptance criteria, all implemented and evidenced
   above. (A)/(B) watcher, (C) handoff, (D)/(E) criteria, (F) review legs.
2. **Scope.** The diff is 22 files, all in the four named sites plus their tests
   and two docs. Three things were deliberately kept out and are recorded in
   Non-goals; the C3 twin is filed as `trg-bd4e75a9` rather than silently left.
3. **Error handling.** Every new external read has a named failure mode that
   degrades to `unknown` or to an infra error — never to a clean answer. The
   blocker probe cannot raise into the watcher; the criteria read fails closed.
4. **Security.** All git calls go through `_run_git` (argument list, no shell);
   GraphQL values are passed as variables, never interpolated; the branch is
   URL-encoded; host-supplied strings are clipped to `MAX_REASON_CHARS` before
   entering output.
5. **Test quality.** Tests assert on outcomes and name the failure they prevent.
   Four pre-existing tests that pinned the mtime contract were rewritten to the
   new contract, not deleted — and one meta-test was tightened, with the
   narrowing verified against all eight real producers rather than assumed.
6. **Naming.** `blockers` / `causes` / `unknown`, `criteria_digests`,
   `classify_reply` — each says what it holds. `_render_pending` is the only
   abbreviation and it sits next to its caller.
7. **Affected Boundaries.** All six carry a test; the three new external shapes
   were additionally probed against the live API.

## Reflection

**The brief's own framing held up, and it was the useful part.** "The check
already holds the information needed to name a cause" turned out to be literally
true in the strongest case: `mergeStateStatus` was already in `_GH_FIELDS`,
fetched on every poll, and read by nothing. Grouping four sites by *defect class*
rather than by module was right — they share one failure mode ("reported a
weaker signal than the evidence supported") and one fix shape ("say what you
know, and say what you could not check"), so the second and third were faster
than the first.

**The one that nearly went wrong was scope, and the brief pre-empted it.**
Item (3) was flagged as highest risk because the traceability manifest is a
frozen contract. Reading the contract first — rather than designing against a
memory of it — showed the whole risk was avoidable: the requirement nodes carry
`spec_path`, and the base commit was already resolved, so the criteria can be
read straight out of git. No schema field, no version bump, no churn in the
committed artifact. The instruction to "scope this one on evidence after reading
the contracts" is what produced that; scoping it up front would have produced a
schema change nobody needed.

**Three probes contradicted the implementation.** The empty-ruleset probe is the
one worth keeping: `GET /rules/branches/<b>` answers `[]` both for "no ruleset"
and for a repo on classic branch protection, so the first version reported
"nothing required is missing" for a repo whose required checks it simply could
not see — the exact false-clean the module exists to prevent, reproduced inside
the fix for it. A module's stated principle does not audit its own code; only
running it against reality did.

**A review of the wrong diff is worse than no review.** The first external code
review ran against `git diff --cached origin/main` while `origin/main` had moved
three PRs ahead of this branch's base, so the diff showed other people's merged
work as deletions. Both reviewers returned confident, well-argued, high-severity
"regressions" in files this change never opens. Nothing in the output marked it
as suspect — the authority of a review is identical whether or not its input was
sane. **In a worktree, always diff against the merge-base, never against a
moving `origin/main`.** This is the same defect class as the four being fixed:
a process reported a strong signal it had not earned.

**The change caught itself, twice.** The new reply classifier flagged the Gemini
leg of this run's own code review as degraded — once truncated at
`finish_reason=length`, once empty — which under the old code would both have
been recorded `success`. And the criteria parser, run over this iterate's own
spec edit, named exactly `FR-01.03` and `FR-01.11`; on `main` today the same
edit reports could-not-determine. Neither was a constructed test.

**What is still owed.** The phase-canon C3 twin still keys on mtime, and
`docs/guide.md` already documents it as content-keyed — the documentation states
a contract the code does not meet. Filed as `trg-bd4e75a9` rather than fixed
here: it has six callers, no `run_id` to key on, and needs a marker designed
rather than ported. The guide line was deliberately left alone; editing it to
match the current behaviour would have papered over the gap.
