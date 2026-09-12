---
run_id: iterate-2026-09-12-pr-review-local-preflight
---

# Mini-Plan: local PR-review preflight (`pr_review.py --base`/`--diff-file`)

## Files to create/modify

- `plugins/shipwright-security/scripts/lib/pr_review_local.py` — new:
  `build_local_diff`, `read_diff_file`, `resolve_diff_mode`, `post_local_result`,
  `PREFLIGHT_BANNER`.
- `plugins/shipwright-security/scripts/tools/pr_review.py` — edit: optional
  `--pr-number`/`--repo`, new `--base`/`--diff-file`/`--project-root`, mode
  dispatch through every branch (empty-diff, truncated, final decision).
- `plugins/shipwright-iterate/skills/iterate/references/F11.md` — edit: new
  local-preflight step before the push.
- `docs/hooks-and-pipeline.md` — edit: one new bullet in the F11 contract list.
- `docs/guide.md` — edit: one clause in step 12 of the `/shipwright-iterate`
  walkthrough.
- `plugins/shipwright-security/tests/test_pr_review_local_preflight.py` — new:
  18 tests (mode resolution, diff building against a real synthetic git repo,
  main() orchestration).

## Work breakdown

1. Read `pr_review.py`, `pr_review_gh.py`, `pr_review_verdict.py`,
   `review_record_tier.py` in full to find the one seam that both modes must
   share (prompts, filter, model call, decision→exit) and the two that must
   diverge (diff source, posting). (done)
2. Confirmed the codebase already has the exact private-temporary-index
   merge-base-diff technique this needs, in `suite_worktree_diff
   .build_worktree_diff` (F0's diff-coverage gate) — re-implemented the
   pattern in a new, smaller module rather than importing that tool's own
   coverage-specific one, to avoid coupling shipwright-security to
   shipwright-iterate's F0 test-suite internals. (done)
3. Add `pr_review_local.py`, then thread `local_mode` through `pr_review
   .main()`'s existing branches one at a time, running the existing 380-test
   suite after each to catch a regression immediately rather than at the end.
   (done — 0 regressions)
4. Write the new test module: pure `resolve_diff_mode` cases first (cheap,
   deterministic), then a real synthetic git repo proving the two hard
   constraints from the brief (untracked files included, a same-named-ref
   commit that landed on the base AFTER the branch point excluded), then
   `main()` orchestration reusing the existing `_wire`-style monkeypatch
   pattern — but asserting the CI-only boundaries are NEVER CALLED (raise if
   reached) rather than merely uncalled-by-omission. (done — 18 tests)
5. Wire the step into `F11.md` right before the push line (not literally
   "right before `deliver_pr.py`" as first phrased — that call happens after
   push, which would forfeit the push+CI round trip this exists to save;
   placed instead as the last local check before delivery begins). Exit 1 =
   STOP; exit 2 = advisory-only, never blocking.
6. Document in `hooks-and-pipeline.md` (the F11 contract bullet list) and
   `guide.md` (step 12), matching how `verify_local.py`'s existing mirror gate
   is documented in both places.
7. Live probe: ran the finished tool against this branch's own diff with a
   real key and `gh` — see the spec's Confidence Calibration. Returned a real
   BLOCK (sensitive-skill-file finding); operator confirmed the design
   in-session per that finding's own request. Not recorded into `reviews.json`
   — the preflight cannot satisfy the gate it precedes.
8. Full plugin suite (`plugins/shipwright-security`) + lint on the touched
   files: 1049 passed, 7 skipped, 0 lint findings.
