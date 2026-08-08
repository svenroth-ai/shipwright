# Mini-Plan: iterate-2026-08-07-shared-op-predicates

**Complexity:** small (classifier: estimate=small, confidence=0.6, prior_source=history,
risk_flags=[]) — matches the operator's own framing ("bewusst ein eigener kleiner Iterate").
**Intent:** CHANGE, routed through **SIMPLIFY sub-mode** (F-simplify) — this is a
behavior-preserving deduplication, not a functional change. Spec Impact = **NONE**.
**Card:** live card is **trg-ca82a057** ("P2.19e [AUTO after P2.19a] Merge the
duplicated git-state predicates", retitled 2026-08-06). Ancestry: split from
trg-79102ee3 (dismissed 2026-08-06, split into P2.19a-e) as P2.19e / trg-de99fdcb
(dismissed same day, retitled for a uniform board — content unchanged, successor
carries the number). Predecessor P2.19a (#588, merged) already did half the work.

*Revision note: this plan was corrected after an internal Opus plan review (see
"Internal review corrections" below) — the corrections are folded into the sections
above/below, not left as a separate errata list.*

## Problem (audit 2026-07-28 finding 29, corrected by the operator 2026-08-05)

`shared/scripts/lib/sweep_outbox.py` and `shared/scripts/lib/reconcile_triage.py` each
gate a destructive commit on the same two git-state predicates:

- `_op_in_progress(root)` — is a merge/rebase/cherry-pick/revert/bisect underway?
- `_has_staged_changes(root)` — is anything staged in the index?

Predecessor P2.19a already extracted `reconcile_triage.py`'s copies (plus `is_detached`
and `path_state_vs_head`) into `shared/scripts/lib/main_tree_guards.py`, and
`reconcile_triage.py` now re-exports them under their historical private names:

```python
from lib.main_tree_guards import (
    has_staged_changes as _has_staged_changes,
    is_detached as _is_detached,
    op_in_progress as _op_in_progress,
)
```

`sweep_outbox.py` was left untouched (`main_tree_guards.py`'s own docstring says so:
*"`lib.sweep_outbox` still carries its own byte-identical `_op_in_progress` copy
(audit 2026-07-28 finding 29, out of this change's scope)"*). It still defines both
predicates locally (`sweep_outbox.py:64-99`, ~34 LOC).

**Correction to the original finding:** its third bullet (`_CI_TRUTHY`/`_ci_active` in
three copies) is stale. All four current call sites (`sweep_outbox.py`,
`reconcile_triage.py`, `gitignore_selfheal.py`, `gitattributes_selfheal.py`) already
delegate to the shared leaf `lib.ci_env.ci_active()` via a thin one-line wrapper, and
say so in their own docstrings. Verified by direct read during Repo Scout — no work
needed there.

**Correction from internal review — the two copies are NOT byte-identical in
behavior, only in the paths both already reach.** Both walk the same three
MERGE_HEAD/CHERRY_PICK_HEAD/REVERT_HEAD refs and the same rebase-merge/rebase-apply/
BISECT_LOG git-path probes, and both fail closed on a `TIMEOUT_RETURNCODE` from
`run_git_soft`. But `main_tree_guards._probe` additionally wraps the call in
`try/except OSError`, mapping an unrunnable git (e.g. binary not on `PATH`) to a
`_UNRUNNABLE` sentinel that both predicates treat as fail-closed; `sweep_outbox.py`'s
local copies call `run_git_soft` bare, and `run_git_soft` (`git_base.py`) only maps
`subprocess.TimeoutExpired` — an `OSError` from `Popen` propagates uncaught. Today
that means an unrunnable git **raises** out of `sweep_outbox_to_branch` (and thus out
of `setup_iterate_worktree` step 5, *after* `git worktree add` has already succeeded),
contradicting the function's own documented contract ("Never raises for an expected
condition — returns a structured `SweepResult`"). After this extraction it becomes a
graceful `skipped`/`op_in_progress` instead. This is a **behavior widening**, not a
pure move: it fixes a latent contract violation as a side effect of deduplication,
not a special-cased new feature. It is called out explicitly (see Ledger row 6 and the
new test below) rather than folded silently into an "identical" claim, and Spec Impact
stays NONE because it touches no FR-observable path (git is not reachably unrunnable in
this call chain — several prior git calls in the same process already had to succeed to
reach the worktree in the first place) and the change is strictly a fail-open→fail-closed
tightening, never the reverse.

## What this iterate does

Mechanical: both predicates already take a `root: Path` parameter, so the extraction is
a pure import swap.

1. **`sweep_outbox.py`** — delete the local `_op_in_progress` (lines 64-92) and
   `_has_staged_changes` (95-99) function bodies; replace with the same re-export import
   `reconcile_triage.py` already uses:
   ```python
   from lib.main_tree_guards import (
       has_staged_changes as _has_staged_changes,
       op_in_progress as _op_in_progress,
   )
   ```
   `run_git_soft` / `TIMEOUT_RETURNCODE` stay imported — the file's later staged-delta
   check (`sweep_outbox.py:226-233`) and commit call (`:240-247`) still use them
   directly and are untouched.

2. **`main_tree_guards.py`** — three docstring corrections (internal review finding),
   **prose only, no signature change** (external review correction — see below):
   - The stale note claiming `sweep_outbox` "still carries its own byte-identical copy"
     becomes false; replace with a note naming all **three** current callers
     (`reconcile_triage` and `triage_gc_publish` — all three guards including
     `is_detached`; `sweep_outbox` — `op_in_progress` + `has_staged_changes`, no
     `is_detached`) instead of the stale "so a SECOND caller can share one copy"
     framing. *(Correction during Stage-1 spec review: this plan draft originally
     said "`triage_gc_publish` — `op_in_progress` only", which is factually wrong —
     `triage_gc_publish.py:29-32` imports and uses all three guards. The actual
     docstring text written never carried that error; only this plan-file
     parenthetical did, now fixed.)*
   - The module title ("a tool that is about to COMMIT in the operator's **main**
     tree") is now half-wrong: `sweep_outbox` commits in a linked **worktree**. Widen
     it to "the tree it is about to commit in" in prose, and clarify at the module
     level (not a per-function docstring line — `main_root` is a shared parameter
     across all four functions here, so the module-level statement is the
     non-duplicative placement, per Stage-1 spec review) that it names the main tree
     for `reconcile_triage`/`triage_gc_publish` but the iterate worktree for
     `sweep_outbox` — **the parameter itself keeps its `main_root` name** (external
     review: OpenAI
     flagged the rename considered in the first draft as scope creep unrelated to
     deduplication and a needless API-shape change for zero behavioral gain; dropped).
     `has_staged_changes`'s docstring also drops its `triage.jsonl`/reconcile-AC-3-specific
     framing now that a second, differently-named caller reads it.
   - Add the `is_detached` asymmetry rationale (see decision section below) as a
     docstring sentence, not just a plan-file note, so the next reader in the code
     itself does not read the asymmetry as an oversight.

3. **Tests** — internal review found **three** tests patch the predicate's git call
   directly by patching `so.run_git_soft`, not two as first drafted:
   - `test_store_git_timeout_paths.py::test_op_in_progress_says_yes_when_it_cannot_tell`
   - `test_store_git_timeout_paths.py::test_sweep_skips_when_the_guard_times_out`
   - `test_main_tree_git_timeout_paths.py::test_op_in_progress_says_yes_when_only_the_gitpath_probe_times_out`
     (missed in the first draft — it sits right next to the already-fixed reconcile
     sibling `test_reconcile_op_in_progress_gitpath_timeout_also_fails_closed` at
     `:207-220` in the same file, which was the tell)

   After the extraction the call moves inside `lib.main_tree_guards`, so each patch
   target moves to `mtg.run_git_soft`, mirroring the reconcile test's already-fixed
   shape. `test_op_in_progress_says_yes_when_only_the_gitpath_probe_times_out` also
   gets the matching re-export identity line
   (`assert so._op_in_progress is mtg.op_in_progress`), same as its reconcile sibling.
   The other two timeout tests in that file
   (`test_staged_probe_timeout_does_not_read_as_a_staged_delta`,
   `test_commit_timeout_is_reported_structurally`) target the *other*, still-local
   staged-delta/commit call sites in `sweep_outbox.py` and need no change.

   **Canonical re-export pin (internal review finding):** the repo already has a
   dedicated contract test for exactly this — `test_triage_write_path_contracts.py`'s
   `_PRIVATE_ALIASES` table + `test_private_aliases_still_point_at_the_shared_implementation`,
   which is what `reconcile_triage`'s moved names are pinned through. Add two rows:
   `("lib.sweep_outbox", "_op_in_progress", "lib.main_tree_guards", "op_in_progress")`
   and the `_has_staged_changes` equivalent. This is the mechanism that actually covers
   `_has_staged_changes`'s identity (the inline assert above only covers
   `_op_in_progress`, co-located with its patch target).

   **New tests for the OSError/behavior-widening branch (internal + external review
   findings):** no existing test exercises `main_tree_guards._probe`'s `except OSError`
   branch at all (grepped — no dedicated `main_tree_guards` unit test file exists).
   Both external reviewers independently pushed on this past the internal review's
   single pin: OpenAI wants the **public** `sweep_outbox_to_branch` outcome verified,
   not only the private predicate; both OpenAI and DeepSeek want `_has_staged_changes`
   covered too, not only `_op_in_progress`. Add three tests to
   `test_store_git_timeout_paths.py`:
   - `mtg.run_git_soft` raises `FileNotFoundError` → `so._op_in_progress(repo) is True`
     (fails closed, does not raise) — the direct pin, cheap and precise.
   - `mtg.run_git_soft` raises `FileNotFoundError` → `so._has_staged_changes(repo) is
     True` — same shape, the other predicate the extraction also changes.
   - `mtg.run_git_soft` raises `FileNotFoundError` (universally, via `sweep_outbox_to_branch`
     end-to-end) → `result.status == "skipped"` and `result.reason == "op_in_progress"`,
     no commit — the **API-level** proof OpenAI asked for: the public contract
     ("never raises for an expected condition") holds, not just the private predicate.

   This is new coverage added *because* the extraction changes reachable behavior —
   the F-simplify escape hatch ("if the code you are simplifying is under-tested, add
   the characterization test first") applied to the shared module, not to
   `sweep_outbox` itself.

## Explicit decision: the `is_detached` asymmetry stays

`reconcile_triage.py` also checks `_is_detached(main_root)` before committing;
`sweep_outbox.py` does not, and this iterate does **not** add it.

- `reconcile_triage.reconcile_main_triage` commits **in the operator's main tree**,
  whose HEAD can legitimately be anything, including detached (e.g. mid-rebase,
  or an operator poking around). A commit there would be unreferenced and lost —
  and it is the operator's **only copy** of that data.
- `sweep_outbox.sweep_outbox_to_branch` commits **in the iterate worktree**, which
  `setup_iterate_worktree.py` always creates on a freshly-checked-out named branch
  (`iterate/<slug>`) — never detached, by construction of the one caller
  (`setup_iterate_worktree.py` step 5, the only production call site; every test
  reaches the sweep the same way via the `make_worktree` fixture helper). There is no
  code path today that reaches the sweep with a detached worktree HEAD.
- **The risk is not symmetric even if it did happen (internal review's stronger
  argument, kept over the plan's original weaker one):** for reconcile, a detached
  commit is the operator's *only* copy — losing the ref loses the data. For the sweep,
  GC (`delivered_membership` / `partition_outbox`) drops an outbox line only once it is
  **present in `origin/<default>`**, so an unreferenced sweep commit still leaves the
  source-of-truth outbox line on disk; the next iterate's sweep simply re-delivers it.
  A detached sweep costs a wasted commit, never lost operator data.

Adding the check would be dead code for the current caller and an unjustified expansion
of scope (F-simplify Five Principles #5, "scope to what changed"). If a future caller
invokes the sweep against an arbitrary (possibly detached) tree, that caller should add
the check then, informed by its own actual risk — not preemptively here.

## Out of scope (named explicitly, not silently dropped)

- `commit_event_followup.py`'s own `has_staged_changes(project_root)` (a *fourth* copy,
  found during Repo Scout) — its docstring says it deliberately "mirrors" rather than
  reuses reconcile's version, and it's the legacy F7 out-of-band path, not part of the
  worktree flow this iterate touches. Not named in the operator's brief.
- **`gitignore_selfheal.py` / `gitattributes_selfheal.py`'s inline op-in-progress
  probes are NOT "same shape" as corrected below — internal review found they fail
  OPEN, not just duplicated:** both files' local `_git()` helper maps a git timeout to
  returncode 124 (non-zero), and both loops then read *any* non-zero as "marker
  absent" (`if returncode == 0: return skipped` / `if returncode != 0: continue`) — the
  exact inverted-fail-safe direction `main_tree_guards.op_in_progress` was hardened
  against. They run in the same worktree, immediately before the step-5 sweep this
  iterate touches (`setup_iterate_worktree.py` calls both self-heals ahead of the
  sweep). This is a real, separate defect, not a documentation gap — deferred here on
  scope grounds (a behavior fix is a CHANGE/BUG iterate, not a SIMPLIFY one) and
  **filed as its own triage card** rather than silently dropped (see below), instead of
  characterized as equivalent duplication.
- `_ci_active` — already unified (see Correction above); no work.
- The audit FINDINGS file (`2026-07-28-triage-delivery-audit-FINDINGS.md`) and the
  P2.19a-era run record (`iterate-2026-08-06-triage-store-write-path.md`) that still
  describe finding 29 as open/three-copies are records of finished runs and are
  deliberately not rewritten (repo's "where documents live" rule: a record of finished
  work is not touched — git history + the live docstring are the sources of truth
  going forward, not the historical record of what was known at the time).

## Test Completeness Ledger

| # | Behavior | Disposition |
|---|---|---|
| 1 | `sweep_outbox`'s op-in-progress guard (merge/rebase/cherry-pick/revert/bisect detection, fail-closed on timeout) behaves identically after delegating to `main_tree_guards.op_in_progress` | `tested` — `test_sweep_outbox_guards.py::test_op_in_progress_in_worktree_skips` (behavior-level, real git) + retargeted `test_store_git_timeout_paths.py::test_op_in_progress_says_yes_when_it_cannot_tell` / `::test_sweep_skips_when_the_guard_times_out` + `test_main_tree_git_timeout_paths.py::test_op_in_progress_says_yes_when_only_the_gitpath_probe_times_out[sweep_outbox]` (timeout fail-closed, all three git-call shapes; the sweep_outbox and reconcile_triage variants of this last test were merged into one `@pytest.mark.parametrize`d test post-code-review — see "Post-review disposition" below — since both now exercise the identical `mtg.op_in_progress` through their two re-export aliases) |
| 2 | `sweep_outbox`'s staged-changes guard behaves identically after delegating to `main_tree_guards.has_staged_changes` | `tested` — `test_sweep_outbox_guards.py::test_staged_changes_in_worktree_skips` |
| 3 | The re-export identity (`so._op_in_progress is mtg.op_in_progress`, `so._has_staged_changes is mtg.has_staged_changes`) is pinned so nobody re-forks a local copy later | `tested` — `test_triage_write_path_contracts.py`'s `_PRIVATE_ALIASES` table (`test_private_aliases_still_point_at_the_shared_implementation`), the canonical mechanism, covers both. (An earlier draft also carried a redundant inline `assert` beside the timeout tests; removed post-code-review as duplicate coverage of the same invariant — see "Post-review disposition" below.) |
| 4 | No regression to `sweep_outbox_to_branch`'s broader behavior (quarantine, GC, CRLF handling, commit) | `untestable` — `covered-by-existing-test`: the full existing `test_sweep_*` / `test_triage_*` / `test_reconcile_*` suite (27 files) is unchanged and re-run as the behavior-snapshot baseline; this diff does not touch any of that logic |
| 5 | `sweep_outbox` still does not check `is_detached` | n/a — not a new/changed behavior (it never checked before; the decision not to add it is documented in prose above and in the `main_tree_guards.py` docstring, not a runtime behavior to pin) |
| 6 | **(new — internal + external review)** `sweep_outbox`'s op-in-progress AND staged-changes guards now fail closed (skip) rather than raising when git itself cannot be run (e.g. binary missing), closing a latent contract violation — proven at both the predicate and the public API | `tested` — three new `test_store_git_timeout_paths.py` cases: `so._op_in_progress` direct pin, `so._has_staged_changes` direct pin (external review: both predicates, not just one), and an end-to-end `sweep_outbox_to_branch` pin proving the public `SweepResult(status="skipped", reason="op_in_progress")` contract (external review: API-level, not only the private predicate) |

## Verification plan

1. **Behavior-Snapshot** (`behavior_snapshot.py snapshot`, scoped to the 27 test files
   that exercise `sweep_outbox` / `reconcile_triage` / `main_tree_guards`, `--target`
   the three touched source files) — before any edit. Note the tool's `--test-cmd` is
   shlex-split with `posix=False` on Windows, which does **not** strip quote
   characters — a quoted multi-word `-m` marker expression comes out with the literal
   quotes still attached and pytest rejects it (exit 4, usage error, easily
   misread as "the baseline is red"). Worked around by using `--deselect` for the two
   known `@pytest.mark.slow` node ids instead of `-m "not slow"`. Captured: 241 tests,
   162206 source LOC baseline.
2. Make the mechanical edits above (TDD: retarget/extend the three timeout tests +
   the two new tests first, confirm they fail against the current local-copy
   implementation, then do the extraction so they go green).
3. **Behavior-Verify** (`behavior_snapshot.py verify`) — green-to-green (plus the new
   coverage), no removed coverage, LOC drops (the ~34 LOC recovered).
4. `uvx ruff@0.15.15 check .` — lint gate.
5. **Full `shared/tests` root as the final, required gate before F0 (external review
   correction)** — the scoped 27-file set stays for fast inner-loop feedback, but is
   not a substitute: `main_tree_guards.py` is a shared leaf with a third consumer
   (`triage_gc_publish.py`) outside the scoped set's direct focus, per OpenAI's review.
   (Already run once during Repo Scout as a pre-flight sanity check: 8593 passed, 28
   skipped, 26 deselected, ~15.5 min — re-run after the edit as the actual gate.)
6. **File a triage card** (not fixed here) for the self-heal fail-open timeout defect
   found during internal review — see "Out of scope" above. Done: `trg-fd3fa3c1`.

## Internal review corrections (Opus plan review, folded in above)

An internal `opus-plan-reviewer` pass (model=opus) against this plan and the five
files it discusses found, and this revision corrects:
- **[high]** a third test breaks, not two (`test_main_tree_git_timeout_paths.py`'s
  gitpath-timeout test) — added to the retarget list.
- **[medium]** the "byte-identical" claim was false — the shared predicate additionally
  fail-closes on an unrunnable git; documented as a deliberate, tested widening rather
  than asserted away.
- **[medium]** the canonical re-export-pin mechanism (`_PRIVATE_ALIASES` table) exists
  and wasn't used — now used for both predicates.
- **[medium]** the planned `main_tree_guards.py` docstring fix was narrower than the
  drift created — title, parameter name, and caller count all needed correcting, not
  just the one stale sentence.
- **[medium]** the self-heal exclusion was mischaracterized as "same shape" when those
  copies fail OPEN (an inverted, more serious defect) — corrected and carded.
- **[low]** the `is_detached` decision's own reasoning was verified correct but its
  weaker argument was upgraded to the asymmetric-risk one.
- **[low]** the triage-card citation (dismissed grandparent → live successor
  `trg-ca82a057`) and an explicit note on why the historical FINDINGS/run-record docs
  are deliberately not rewritten.

## External review corrections (OpenAI + DeepSeek via OpenRouter, folded in above)

Ran `external_review.py --mode iterate` against this (already internally-corrected)
plan and a spec surrogate built from the driving triage card
(`iterate-2026-08-07-shared-op-predicates-spec-surrogate.md`, since small-complexity
SIMPLIFY runs have no iterate-spec file to compare against). Verdicts: DeepSeek
**approve**, OpenAI **revise** (not a contradiction — "agree within one step" per the
tool's own comparator). Findings, and what this revision does with each:

- **[medium, OpenAI]** Test the OSError fail-closed change at the **public**
  `sweep_outbox_to_branch` API, not only the private predicate. **Adopted** — added an
  end-to-end pin (Ledger row 6).
- **[medium, OpenAI + low, DeepSeek]** The new OSError coverage only pinned
  `_op_in_progress`; `_has_staged_changes` goes through the same `_probe` path and
  changes the same way but had no test. **Adopted** — added the direct pin.
- **[low, OpenAI]** The `main_root` → `root` parameter rename (added during the
  internal-review fold-in, to make `main_tree_guards.py`'s docstring accurate) is
  unrelated to deduplicating the predicates and is an unforced API-shape change for a
  module with callers this diff doesn't otherwise touch. **Adopted — reverted.** The
  docstring accuracy problem the rename was chasing is fixed in prose only (the
  parameter's own docstring line now says which tree it names for which caller); the
  signature is untouched. This also moots DeepSeek's companion request (grep for
  leftover `main_root` references after the rename) — there is no rename to leave
  leftovers.
- **[low, OpenAI]** The verification plan let "the scoped 27-file set" stand in for
  the full `shared/tests` suite as an alternative final gate. **Adopted** — the full
  suite is now the required final gate; the scoped set is inner-loop-only.
- **[medium, OpenAI]** Don't call the extraction "mechanical"/pure behavior-preserving
  without qualifying the OSError branch; the "unreachable in practice" argument isn't
  a complete guarantee. **Already addressed** by the internal-review fold-in (the
  Problem section already calls this out as "a behavior widening, not a pure move" with
  its own Ledger row) — no further plan change needed, noted here so the disposition is
  explicit rather than silently satisfied.

Full review cascade (`spec-reviewer` → `code-reviewer` → `doubt-reviewer`) with
`model=opus` runs next, per explicit operator instruction, despite small + no risk
flags normally gating Full Code Review to "only if risk flags".

## Post-review disposition (code-reviewer + doubt-reviewer, model=opus, folded in)

**Stage 1 (spec-reviewer):** PASS, no changes requested (see `spec-review.json`).

**Stage 2 (code-reviewer):** 3 findings, all fixed —
1. The bloat-adjacent overage this diff's own retargeted test left in
   `test_main_tree_git_timeout_paths.py` was resolved by merging the sweep_outbox
   and reconcile_triage variants of the gitpath-timeout test into one
   `@pytest.mark.parametrize`d test (both exercise the same `mtg.op_in_progress`
   through its two aliases — a genuine duplication the extraction itself created),
   landing the file at 297 lines. (An earlier attempt — reverting to the file's
   exact pre-existing 304 — did NOT clear the session's bloat Stop-hook, which
   blocks on any session-touched file currently over the limit, not only growth
   past a baseline entry; see the `## Learnings` entry this run added.)
2. `test_sweep_skips_when_git_is_unrunnable_end_to_end`'s docstring narrowed to
   name exactly what it proves (the guard seam via `mtg.run_git_soft`), not
   `sweep_outbox.py`'s 3 other untouched bare `run_git_soft` call sites.
3. The duplicated `_unrunnable` closure hoisted to module level in
   `test_store_git_timeout_paths.py`, beside the existing `_timeout` helper.

**Stage 3 (doubt-reviewer):** 2 doubts, both fixed with docstring-only precision
(no behavior change) —
1. `main_tree_guards.py`'s `is_detached` asymmetry paragraph extended to name the
   drift-adoption side effect (`sweep_drift.commit_main_tracked_drift` writes to
   the outbox durably, before the worktree commit) that the original justification
   omitted — independently verified against `sweep_drift.py:252-291` before fixing.
   The conclusion ("no data loss, just a wasted commit") held; only the stated path
   to it was incomplete.
2. `_probe`'s docstring now notes the dropped `OSError` diagnostic string is
   deliberate — every caller's hazard name already means "could not confirm this
   is safe", not "confirmed this specific hazard".

Full disposition detail in `.shipwright/planning/iterate/iterate-2026-08-07-shared-op-predicates/{code-review,doubt-review}.json`.
