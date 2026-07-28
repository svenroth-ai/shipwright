# Iterate Spec: the revert check stops accusing edits and main's own deletions

- **Run ID:** iterate-2026-07-28-silent-revert-false-positives
- **Type:** bug · **Complexity:** medium
- **Risk flags:** none from `classify_complexity` (message stage). `cross_component`
  and `touches_ci_supplychain` are diff-driven and recomputed at F11 — confirmed
  below against `risk_detectors` once the diff existed.
- **Affects:** FR-01.11 (`/shipwright-iterate`) — folds into the existing
  `(iterate-2026-07-27-no-silent-revert)` criterion. **Spec Impact: MODIFY.**
- **Source:** `HANDOVER-2026-07-28-silent-revert-false-positives.md`
  (found during `iterate-2026-07-27-checks-that-gate-nothing`, PR #475).

## The bug

`check_no_silent_revert` (shipped in #477) refuses a hand-over when the branch's
tree is missing content the default branch gained while the branch was open. It
reported **four** such findings in one run, and all four were wrong. Each was
cleared through the escape hatch (`declared_removals`), which is the actual
danger: an escape hatch that becomes routine turns the gate into decoration —
the disease card `trg-c7e5835b` was about.

**The check is worth keeping and must not be weakened.** It is the reason the
real landmine (#463: a stale copy overwriting four merged PRs' documentation)
is now catchable at all.

## Root cause

`dropped_lines` decides "dropped" by whole-line set subtraction, evaluated **per
integration merge** but always **against the branch's final HEAD**:

```python
gained  = theirs - (_file_lines(root, base, path) or set())   # what main added
ours    = _file_lines(root, head, path)
missing = gained if ours is None else gained - ours
```

Two things that are not losses satisfy `gained - ours`:

**(A) The default branch itself removed the text afterwards.** Merge 1 delivers
`main@X`. A later `main` commit deletes or rewrites that text. The branch
integrates again and correctly no longer carries it — but merge 1 is still
scored against HEAD, so it reads as a loss. Nothing was dropped: main does not
have it either.

**(B) The branch edited a line in place.** The comparison is over whole lines,
so adding a sentence to a table row makes the row's previous text read as
dropped. The (A) filter cannot help here — main still has the old line.

**(C) Found while investigating, and it decides whether (A) can be fixed at
all.** The F11 call site is `check_silent_revert_for_run(project_root)`, which
takes `default_branch="main"` — the *local* branch. Branches are integrated from
`origin/main` (`ensure_current` merges `origin/<default>`). When the local ref
lags, `merge-base --is-ancestor <merged-parent> main` fails and **the whole
integration merge is skipped**. Measured on the real branch: 6 integration
merges seen against the current tip, 2 against a tip one commit older, 1 against
a tip three older. A stale ref quietly shrinks the check — and it also makes the
(A) filter, which asks "does main still carry this line?", answer against the
wrong tree.

## Reproduction (real history, not synthetic)

`origin/iterate/checks-that-gate-nothing` (the #475 branch, pre-squash) is still
in the object store. Against the main tip of that moment (`ea2ad4bf`) the
shipped detector reproduces **exactly** the four declared findings:

| Path | lines | still on main's tip? | case |
|---|---|---|---|
| `.shipwright/planning/iterate/2026-07-27-review-floor-not-chained.md` | 6 | 0 of 6 | A |
| `shared/tests/test_record_review_pass_cli.py` | 25 | 0 of 25 | A |
| `.shipwright/planning/iterate/iterate-2026-07-27-project-granularity-basis/reviews.json` | 4 | 0 of 4 | A |
| `docs/hooks-and-pipeline.md` | 1 | 1 of 1 | B |

The two cases separate cleanly on one observable: **is the line still on the
default branch's own tip?** 35 of 36 lines are case (A); the single case (B) line
is the `triage.outbox.jsonl` producer row.

## The fix

Three proofs on `missing`, each provable rather than fuzzy, plus the ref repair.
Cheapest and strongest first; every one can only ever REMOVE findings, so every
one has to be a proof.

**Proof 1 — the two trees already agree about this file.** If this branch's
version of the path is identical to the default branch's (or both are absent),
nothing in it can be a loss. This is exactly what the operator who first hit
these false positives checked by hand: *"`git diff origin/main HEAD -- <path>` is
EMPTY for every path listed."* It settles all three real case-(A) paths outright.

**Proof 2 — the default branch moved past the line, and this branch followed.**
Between the merge that delivered the line and the tip, the default branch either
deleted it outright or replaced it — and where it replaced it, this branch
carries the replacement. Either way both trees end in the same place.
*The second half is load-bearing*: "the tip no longer has this exact line" is
equally true when the default branch merely fixed a typo in a line this branch
really had reverted. Requiring the branch to carry what superseded it tells the
two apart.

**Proof 3 — the line was edited, not discarded.** Positional, not similarity
scoring. In the minimal-context (`-U0`, whitespace-insensitive) diff of
`tip..HEAD`, the **same hunk that deletes the line** must add a line `L'` where

- (a) the line's **tokens appear in order** inside `L'`, **and**
- (b) `L'` is in neither that merge's base **nor the branch's own pre-merge
  side** — it must be something this branch could only have written *after*
  seeing theirs.

The hunk pairing makes this evidence rather than coincidence; `-w` keeps the
hunks from swelling to the whole file on a reformat; and (b) stops the two ways
a replacement can be a fake witness — a resurrected pre-merge line, and a line
the branch already had before the content it now vouches for existed.

**The ref repair (the (C) defect).** Resolve the default branch to the ref the
branch actually integrates: prefer `origin/<name>` when it resolves *and* the
local `<name>` is an ancestor of it. Diverged, locally-ahead, git failure, or no
remote (the test repos): keep the local ref. The resolved ref is also what the
operator is told about, so the message can never name a ref the comparison did
not use.

**File-absence semantics, stated once.** This module already reads a `None` from
`_file_lines` as "the path is not at that ref" (`theirs is None` → skip;
`ours is None` → the branch deleted the file, report). The filters follow the same
convention: absent at the tip means main carries *none* of it, so Filter 1
silences the whole path; absent on our side means there is no line that could
carry anything forward, so Filter 2 does not apply.

### What the external plan review changed

Both reviewers were run (`external_review.py --mode iterate`); OpenAI returned
**revise**, Gemini's reply was truncated by the provider but its one finding
arrived intact and is the most consequential of the round.

1. **Gemini — Filter 2 would mask a short-line revert.** If main added `break`
   and the branch deleted it while authoring any new line containing that token,
   the earlier "any newly-authored line in the file" formulation silenced a real
   revert. Gemini proposed a minimum token count; a threshold is exactly the
   arbitrary knob this spec set out to avoid, so the filter was made **positional**
   instead — the added line must be in the same `-U0` hunk as the deletion.
   Re-measured on the real branch: still 35 + 1 silenced, 0 residue.
2. **OpenAI, high — Filter 1 ignored a file main had deleted.** `tip is None`
   preserved every line for that path, which is precisely a "main does not carry
   it" case. Now silences the whole path.
3. **OpenAI, high — Filter 2 would crash when the branch deleted the file.**
   `ours - base_lines` with `ours is None` is a `TypeError`, reachable from the
   existing `test_deleting_a_file_after_taking_their_work_is_reported`. Filter 2
   is now skipped when our side is absent.
4. **OpenAI, medium — empty token sequence.** A zero-token needle is a
   subsequence of everything. It cannot occur (`_significant` drops blank lines
   before they ever reach the filter), but the helper returns `False` explicitly
   rather than resting on that.
5. **OpenAI, medium — ref resolution must distinguish "not an ancestor" from a
   git failure.** Only `rc == 0` upgrades to `origin/<name>`; every other outcome
   keeps the local ref. Pinned by AC5.
6. **OpenAI, low — repeated `git show` for the same path** across integration
   merges. Both per-path lookups are memoised for the call.
7. **OpenAI, low — no shell interpolation.** `_run_git` is argv-based and is the
   only git path used; no new remote or network operation is introduced.

### What the review cascade changed

The build was green, the four real false positives were gone, and the motivating
failure still blocked. Everything below was found afterwards. **Stage 3 disproved
the design** — all four of its constructions returned "nothing was dropped"
against the version that had already passed Stage 1 and Stage 2.

**Stage 1 — spec-reviewer: approve, 2 medium.** The plain-language requirement
text I folded into FR-01.11 claimed more than the code does (it read as covering
the resurrection case, which is still reported) and stated an absolute the code
deliberately does not always honour (the ref fallbacks). Both corrected. Also
corrected the mini-plan, which still said "one production file" after the
300-line cap forced a split.

**Stage 2 — code-reviewer: revise, 1 high.** A `git show` failure and a genuinely
absent path both produced `None`, and `None` silenced the whole path — so an
unreadable file would have come back as a **green pass** on a comparison that
never happened, in a module that turns exactly that situation into a visible SKIP
everywhere else. `ls-tree` now separates absence from failure. Also: an
inversion-prone name (`merely_edited` returned the lines that were *not* merely
edited), a duplicated `_file_lines`, token re-splitting in the inner loop, and
two of my own tests that pinned nothing.

**Stage 3 — doubt-reviewer: revise, 4 high.** Each was reproduced before fixing
and is now a permanent test in `test_silent_revert_not_weakened.py`:

| # | The real revert that went green | Fix |
|---|---|---|
| D1 | **The check's own motivating test**, with the branch line reworded to mention what it discards. The branch wrote that line *before* ever seeing theirs, so it cannot be the replacement — but the pairing could not tell. | exclude the branch's pre-merge side |
| D2 | Same hole at scale: one long pre-existing line clears *both* bullets the default branch added, from a single hunk. | same |
| D3 | A whitespace-only reindent makes `git diff -U0` call every line changed, collapsing the file into ONE hunk in which any addition vouches for any deletion 28 lines away. | diff with `-w` |
| D4 | The default branch fixes a typo in a line this branch really reverted; the exact string vanishes from the tip and the finding with it. | require the branch to carry what superseded it |

D4 is why the case-(A) filter is no longer "is this line still on the tip?" — a
line-level absence test cannot tell "they superseded it" from "they touched it".
It became Proof 1 (whole-file agreement) plus Proof 2 (superseded *and* followed).

Two further Stage-3 findings were accepted rather than fixed, and are recorded
rather than left implied: a SKIP no longer swallows findings (fixed — findings
are reported with the incomplete comparison noted alongside), and token
containment proves words survive but **not meaning** (accepted, bounded on three
sides, pinned by `test_the_accepted_blind_spot_is_pinned_not_implied`).

### Rejected alternatives

- **Character-level subsequence instead of token-level.** Measured: it produces
  **3 accidental matches** among the case-(A) lines on the real branch — a short
  line is a subsequence of many longer ones. Rejected on evidence.
- **Plain substring containment.** Fails the actual case (B): the sentence was
  inserted mid-row, so main's line is not a substring of the branch's. Measured
  `False` on the real line.
- **`git merge-tree` against the current tip** (the handover's own suggestion).
  Does not work: once the branch has integrated, `merge-base(tip, HEAD) == tip`,
  so the three-way merge is a fast-forward whose result *is* HEAD's tree. It
  would report "clean" for #463 itself. Recorded so it is not re-attempted.
- **Comparing the net `tip..HEAD` diff instead of per-merge.** Fixes (A) only;
  case (B) is on the tip, so it survives. Also discards the "content the branch
  had a chance to keep" scoping the current framing is built on.
- **Fix (A) only and accept one declaration per long branch.** Rejected: an
  edited-line false positive recurs on every doc-table edit, which is routine.

## Acceptance criteria

**Must stop being reported** *(the bug)*

- **AC1** A line the default branch superseded itself, where this branch carries
  what superseded it, is not reported. *(case A)*
- **AC1b** A path the default branch deleted outright is not reported — it
  carries none of it.
- **AC2** A line whose words survive, in order, inside the line that replaced it
  *in the same hunk* is not reported. *(case B)*

**Must still be reported** *(the gate must keep its teeth)*

- **AC3** A resurrection: the replacing line is the pre-merge version from that
  merge's base.
- **AC4** A coincidence: the matching line is in a **different** hunk.
- **AC4b** A file the branch deleted while the default branch still has it.
- **AC4c** *(D1/D2)* A replacement the branch wrote **before** the line it
  vouches for existed — i.e. present on the branch's own pre-merge side. One such
  line must not clear several deleted ones.
- **AC4d** *(D3)* A finding must survive a whitespace-only reformat of the file.
- **AC4e** *(D4)* A line the default branch merely edited afterwards, where this
  branch carries neither version.
- **AC6** The #463 shape is still caught — the 16 pre-existing tests stay green
  and **unmodified**.

**Fail-honest**

- **AC5** The default branch resolves to `origin/<name>` when that ref exists and
  the local ref is behind it; diverged, locally-ahead, git failure or no remote
  keeps the local one. The ref reported to the operator is the one compared.
- **AC5b** A side that cannot be read suppresses nothing: with findings, they are
  reported and the incomplete comparison noted alongside; with none, the check is
  a visible SKIP, never a pass.

**Environment**

- **AC7** Verified in its own environment: run against **this** branch after
  integrating main, per
  `feedback_gate_must_be_verified_in_its_own_environment`.

## Affected Boundaries

- `shared/scripts/tools/verifiers/silent_revert.py` — the detector; consumed by
  `verifiers/iterate_checks.py` at F11.
- Git object store (read-only: `show`, `rev-list`, `merge-base`, `diff`).
- `shipwright_test_results.json → iterate_latest.declared_removals` — the escape
  hatch, unchanged in shape; the point of the fix is that it stops being needed.
- No config file, no env var, no hook, no workflow is touched.

## Test Completeness Ledger

Principle: **testable ⇒ tested.** 46 tests over four files — 16 pre-existing and
untouched, 30 new. Every behaviour this diff introduces or changes:

| # | Behaviour | Disposition | Evidence |
|---|---|---|---|
| 1 | Two trees agreeing about a file clears it | `tested` | `test_a_line_main_itself_deleted_later_is_not_a_drop`, `test_the_check_passes_once_the_false_positives_are_gone` |
| 2 | A path the default branch deleted outright clears | `tested` | `test_a_file_main_itself_deleted_later_is_not_a_drop` (asserts it IS reported first) |
| 3 | Superseded **and** followed clears a line | `tested` | `test_a_line_main_itself_deleted_later_is_not_a_drop` |
| 4 | Superseded but **not** followed still reports | `tested` | `test_a_typo_fix_on_the_default_branch_cannot_erase_a_finding` (D4) |
| 5 | A line edited in place clears | `tested` | `test_extending_a_line_main_added_is_not_a_drop` |
| 6 | A resurrected pre-merge line still reports | `tested` | `test_restoring_the_pre_merge_version_is_still_reported` |
| 7 | A match in a different hunk does not count | `tested` | `test_a_match_in_a_different_hunk_does_not_carry_the_line_forward` |
| 8 | A replacement from the branch's pre-merge side does not count | `tested` | `test_a_branch_line_that_merely_mentions_what_it_discards` (D1) |
| 9 | One such line cannot clear several deletions | `tested` | `test_one_pre_existing_line_cannot_vouch_for_several_deleted_ones` (D2) |
| 10 | A whitespace reformat cannot widen a hunk | `tested` | `test_a_whitespace_reformat_cannot_widen_a_hunk_into_the_whole_file` (D3) |
| 11 | A file the branch deleted still reports | `tested` | `test_deleting_a_file_main_still_has_is_reported` |
| 12 | Ref: local behind → `origin/<name>` | `tested` | `test_default_ref_prefers_origin_when_the_local_ref_is_behind` |
| 13 | Ref: locally ahead / diverged / no remote → local | `tested` | same + `test_a_diverged_origin_keeps_the_local_ref`, `test_default_ref_falls_back_when_there_is_no_remote` |
| 14 | The operator message names the ref actually compared | `tested` | `test_the_message_names_the_ref_that_was_actually_compared` |
| 15 | `tokens_in_order`: empty needle, over-long needle, order, whole tokens, repeats | `tested` | 5 unit tests in `test_silent_revert_filters.py` |
| 16 | The accepted blind spot (words ≠ meaning) | `tested` | `test_the_accepted_blind_spot_is_pinned_not_implied` — a pinned decision, not a guarantee |
| 17 | `replacement_hunks`: deleted `---` is not the diff header; no-diff, unreadable ref and binary all yield `[]` | `tested` | 4 unit tests |
| 18 | `tip_state` separates present / absent / unreadable | `tested` | `test_an_absent_path_and_an_unreadable_one_are_told_apart` |
| 19 | An unreadable side suppresses nothing and is disclosed | `tested` | `test_a_side_that_cannot_be_read_suppresses_nothing`, `test_an_unreadable_delivered_side_is_disclosed_not_inferred` |
| 20 | Findings survive an incomplete comparison; no findings → visible SKIP | `tested` | `test_an_unreadable_path_does_not_swallow_a_real_finding`, `test_an_unreadable_path_with_no_findings_is_a_visible_skip` |
| 21 | The #463 shape is still caught | `tested` | the 16 pre-existing tests, unmodified, plus a real-scale probe below |
| 22 | Behaviour on this repo's real history (probe 1, 7, 9) | `untestable` — `covered-by-existing-test` | the shapes are pinned by rows 1–11; the probes are corroboration on real data, not a separate behaviour, and cannot be a unit test because they need this repository's own history |

**0 testable-but-untested.** Per-path memoisation and the module split are not
behaviours and carry no row.

## Confidence Calibration

- **Boundaries touched:** the F11 verifier `silent_revert.py` and its git reads;
  no I/O contract, no config, no hook. `touches_io_boundary` does not fire (the
  file's `json.loads` in `declared_removals()` is pre-existing and untouched).
- **Empirical probes run:**
  1. *Reproduced the bug on real history* — the shipped detector against
     `origin/iterate/checks-that-gate-nothing` @ tip `ea2ad4bf` returns exactly
     the four paths the #475 run declared. Not a synthetic approximation.
  2. *Case split measured* — 35 of 36 flagged lines are absent from main's tip
     (case A); 1 is present (case B). The split is observable, not assumed.
  3. *Character-level subsequence falsified* — 3 accidental matches among the
     case-(A) lines. Rejected on measurement, not taste.
  4. *Substring containment falsified* — `False` on the real case-(B) line
     (insertion is mid-row, common prefix 1011 of 2409 chars).
  5. *The (b) guard shown to bite* — one case-(A) line in
     `test_record_review_pass_cli.py` matches by token subsequence but is
     rejected by the base guard. The guard is load-bearing, not decorative.
  6. *Stale-ref shrinkage measured* — 6 / 2 / 1 integration merges seen as the
     default-branch ref is walked back. This is what made (C) in scope.
  7. *Final predicate, whole branch* — **0 residue** on all four real paths.
  8. *The motivating failure, at real scale* — the #463 shape reconstructed from
     two genuine versions of the 2,700-line `docs/hooks-and-pipeline.md` it
     damaged (its own branch was squash-merged away, so it cannot be replayed
     directly). Still blocks, 185 lines. Re-run after every redesign.
  9. *Four adversarial disproofs* — Stage 3 built four real reverts that the
     design let through. All four reproduced, fixed, and pinned.
  10. *Own environment (AC7)* — the fixed check run against **this** branch after
     integrating main (5 commits behind at the time): it resolved `origin/main`
     rather than the stale local ref, saw the integration merge, and passed with
     an empty `declared_removals` — the first long branch since #477 that needed
     none. Disclosed: the branch was then **rebuilt on `origin/main`** to keep the
     eleven derived snapshots out of the iterate commit
     (`check_no_derived_snapshots_committed`), and `main` moved again during
     review, so it integrated once more. What ships therefore carries an
     integration merge of its own, and the gate was re-run on **that** — resolved
     `origin/main`, 1 merge seen, nothing dropped, no declaration needed. Run
     three times across three different branch shapes, same answer each time.
- **Test Completeness Ledger:** see the table above.
- **Confidence-pattern check:**
  - *Asymptote (depth)* — the honest reading is that depth was **not** reached by
    building carefully: the design was green, matched the real data, and was
    still wrong. Stage 3 disproved it with four constructions, and the fourth
    reshaped the whole case-(A) approach. What raises confidence now is that
    those four are permanent tests rather than a memory of an argument.
  - *Coverage (breadth)* — both false-positive classes, all four guards that keep
    the edit proof from becoming a loophole, all four ref-resolution outcomes,
    all four read sides' failure paths, and the unchanged true-positive suite.
  - *Integration composition* — `cross_component` is evaluated against the diff
    at F11; `silent_revert.py` is not in `CROSS_COMPONENT_FILE_PATTERNS` (it is a
    verifier, not the merge/churn/event-log resolver), so no integration-coverage
    obligation. Confirmed against `risk_detectors`, recorded at F11.
