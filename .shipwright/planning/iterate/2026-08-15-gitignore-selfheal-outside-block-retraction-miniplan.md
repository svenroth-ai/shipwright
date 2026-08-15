# Mini-Plan: gitignore self-heal retraction scoped to the managed block

- **Run ID:** iterate-2026-08-15-gitignore-selfheal-outside-block-retraction

## Files to create/modify

| File | Change |
|---|---|
| `shared/scripts/lib/gitignore_canon.py` | edit — `_strip_superseded` retracts a superseded-rule match **inside the managed BEGIN/END block (unchanged) or before it — never after**. Three marker shapes, not two: zero BEGIN/zero END (no block yet — a valid "not yet scaffolded" shape, not malformed) strips anywhere in the file so a fresh block can be created with its replacements in the same pass; exactly one BEGIN and exactly one END, in that order (`begins[0] < ends[0]`), extends the scope to inside-or-before; anything else (duplicate, unmatched, or reversed markers — genuinely malformed) falls back to the original, strictly inside-the-block-only scope. Kept as a single inline function, not a separate module — an earlier extraction attempt (`gitignore_retract.py`) was reverted after it broke `write-project-config.py`'s dotted-import consumption path (a `sys.modules['lib']` cross-plugin collision); see the iterate spec's Round 3 "Module-split attempt" note. File trimmed to exactly 300 lines via docstring edits instead. |
| `shared/tests/test_gitignore_canon_retraction.py` | edit — replace `test_merge_does_not_retract_a_rule_outside_the_managed_block` (asserted the old, now-wrong contract) with `test_merge_retracts_a_superseded_rule_before_the_managed_block`; add `test_merge_preserves_a_superseded_match_authored_after_the_block`, `test_merge_retracts_a_superseded_rule_with_no_managed_block_yet`, `test_merge_falls_back_to_inside_only_scope_on_duplicate_markers` |
| `shared/tests/test_gitignore_selfheal.py` | edit — extract both retraction tests into the new sibling file (kept the file under the 300-line guideline; it was already at 322 before this change) |
| `shared/tests/test_gitignore_selfheal_retraction.py` | new — sibling split (mirrors the existing `test_gitignore_canon_retraction.py` / `test_gitignore_canon_merge.py` split), holds the inside-block test (moved, unchanged) + a new before-block/pre-marker-era test reproducing shipwright-webui's real shape, with a containment assertion (narrow replacements still ignore `INDEX.md`) |

## Work breakdown

1. Reproduce the defect directly against the live `shipwright-webui` checkout
   (`git blame`, `git log -S`) to confirm the rule's actual position and
   dates — done in the investigation, captured in the iterate spec's Root
   Cause section.
2. Write the failing test (`test_merge_retracts_a_superseded_rule_before_
   the_managed_block`) proving `_strip_superseded` cannot reach a superseded
   rule outside the block. Confirm red.
3. Fix `_strip_superseded` to also retract a match found **before** the
   first BEGIN marker (never after it), falling back to the original,
   strictly inside-the-block-only scope on a malformed target (duplicate
   BEGIN/END markers). Confirm the new test and the full retraction suite
   go green.
4. Add the end-to-end `self_heal_gitignore` regression test for the exact
   webui shape (unwrapped stale line ahead of a separately-scaffolded block,
   with a containment assertion that the narrow replacements still ignore
   `INDEX.md`) and confirm it exercises the real commit path, not just the
   pure planner. Verify it is genuinely red against the pre-fix code
   (`git stash` the lib change, re-run, confirm the failure, restore).
5. Add the two narrowing regression tests the external review's first round
   asked for: a superseded match placed AFTER an established block is
   preserved; a target with no managed block at all still retracts (and
   creates a fresh block). Add the malformed-marker fallback test the second
   round asked for.
6. Split `test_gitignore_selfheal.py`'s two retraction tests into a new
   sibling file to keep both files under the 300-line guideline (mirrors an
   existing repo convention rather than inventing a new one).
7. Re-run the full gitignore-canon/self-heal suite (8 files, 61 cases) plus
   `test_triage_scaffold.py` (an unrelated consumer of the same self-heal
   pattern, sanity-checked for interference), the full `shared/tests/` suite
   (9234 cases), and `ruff check` on all touched files.
8. External review round 3 tightened the malformed-marker check (exactly
   one BEGIN + exactly one END + `begins[0] < ends[0]`, not two independent
   `<=1` checks) and declined a proposed "independent ownership signal"
   requirement as out of scope (reasoning in the iterate spec's Round 3
   section). A resulting attempt to extract `_strip_superseded` into its
   own module to relieve line-count pressure was reverted after it broke
   `write-project-config.py`'s dotted-import path via a `sys.modules['lib']`
   collision — kept inline instead, trimmed to exactly 300 lines via
   docstrings. Both the gitignore suite and the full `shared/tests/` suite
   were re-run green after the revert.
9. Update the iterate spec's Confidence Calibration + Test Completeness
   Ledger with the actual evidence, then proceed to Self-Review / the review
   cascade / finalization.

## Test strategy

- Unit/functional tests only (pure Python library + git-fixture-backed
  integration tests already established in this test suite) — no E2E needed
  (Verification surface = `none`, justified in the iterate spec: no
  web/cli/api surface of its own).
- TDD: failing test written and confirmed red before the fix (step 2 above).
- Full existing suite re-run (not just the touched files) to catch any
  consumer relying on the old "outside-block lines are always left alone"
  contract.

## Alternative approach (considered, rejected)

**Detect plugin-cache staleness and warn/refuse instead of (or in addition
to) broadening the retraction scan.** Rejected because (a) the investigation
proved the defect reproduces against a byte-identical, fully current
template — staleness is not the operative cause here, so a staleness
detector would not have fixed shipwright-webui's actual bug; and (b) a
freshness signal is not buildable from purely local comparison in the first
place, because the code that would judge staleness (`gitignore_canon.py`)
and the template it would judge both live in the same unversioned `shared/`
cache tree and are refreshed atomically together — there is no independent,
locally-available oracle for "how old is my own copy" (the code's idea of
"current" is definitionally whatever its own bundled template says). A real
fix for that class would need an external signal (e.g. comparing the
marketplace clone's age against a threshold) — genuinely useful, but a
different, separable problem from the one this card asked to root-cause, and
explicitly out of scope per the card ("do not build the retraction
mechanism... the question is why the heal never reached main").
