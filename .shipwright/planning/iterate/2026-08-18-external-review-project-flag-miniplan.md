# Mini-Plan: external-review-project-flag

- **Run ID:** iterate-2026-08-18-external-review-project-flag

## 1. Files to create/modify
- `shared/tests/test_external_review_project_flag.py` — new, repo-wide static regression test (rewritten from an initial fixed-file design — see §5)
- `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md` — edit (1 call site + the canonical `{plan_plugin_root}` resolution/failure-handling note)
- `plugins/shipwright-iterate/skills/iterate/references/iteration-planning.md` — edit (2 call sites)
- `plugins/shipwright-iterate/agents/sub-iterate-runner.md` — edit (2 call sites + new `plan_plugin_root` Input parameter + Branch B failure-handling note)
- `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` — edit (document `plan_plugin_root` threaded into the runner spawn)
- `plugins/shipwright-build/skills/build/references/code-review.md` — edit (1 call site + pointer to the canonical failure-handling note)
- `shared/scripts/tools/external_review.py` — edit (its own module-docstring Usage example was a 10th, undiffed mention of the unflagged invocation — AC-1)

## 2. Work breakdown
1. Grep all 3 plugins for `external_review.py` invocations; confirm exact
   inventory against the card's claim (6 broken sites, 3 already-correct in
   shipwright-plan). Confirmed via `grep -rn`.
2. Confirm `{plan_plugin_root}` is already in scope (used for
   `--plugin-root`) at 4 of the 6 sites (iteration-reviews.md,
   iteration-planning.md x2, code-review.md) — those just need `--project`
   added inline.
3. Confirm `{plan_plugin_root}` is NOT in scope for the 2
   `sub-iterate-runner.md` sites (only `{plugin_root}`, which is
   shipwright-iterate's own root, is a declared Input parameter) — thread
   it in as a new Input parameter rather than inventing a monorepo-only
   path, per the card's explicit instruction.
4. Write the static regression test FIRST (TDD, Path C) asserting
   `--project` on every invocation block, initially over a fixed 4-file
   allowlist; confirm it fails against the unfixed docs (4/4 red).
5. Apply the `--project "{plan_plugin_root}"` fix at all 6 sites; re-run
   the test (4/4 green).
6. Empirically verify the fix from a directory with no `pyproject.toml`
   (the actual leadwright failure mode) — plain `uv run` fails,
   `uv run --project` succeeds.
7. Trim added lines against the two bloat ceilings the edits crossed
   (`sub-iterate-runner.md` at 497/497, `campaign-mode.md` at 400/400 —
   both zero-headroom baselines) rather than raising them.
8. Run full plugin test suites (`shipwright-iterate`, `shipwright-build`)
   + `shared/tests` + `ruff` + `verify_local.py`; confirm no regressions.
9. **Post-internal-plan-review revision:** rewrite the test off the
   fixed-file allowlist into a repo-wide `rglob` scan of `plugins/`+`shared/`
   (finding 4), add the producer/consumer contract tests and the
   canonical-note existence test (findings 1/3), thread the
   `{plan_plugin_root}` resolution + `uv run`-failure note into
   `iteration-reviews.md` and point every other call site at it (finding 1),
   re-probe the fix against the installed plugin-cache copy in addition to
   the monorepo copy (finding 6), and reclassify Verification `none` → `cli`
   (finding 10). Re-run steps 6-8 after.
10. **Post-external-code-review revision:** strengthen the test's
   `--project` check from "appears anywhere in the block" to "is the token
   immediately after `uv run`, before the script path, with an allowed
   value" — a `--project` placed after the script path parses as a script
   argument, not uv's own flag, and would have silently passed the looser
   check while doing nothing. Re-run steps 6-8 after.

## 5. Test strategy
- New static test (`test_external_review_project_flag.py`) is the primary
  evidence. **Revised after internal plan review (finding 4):** the first
  version parametrized over a fixed 4-file allowlist; that inverts the
  guard — a call site added anywhere else ships unprotected. Rewritten to
  `rglob` the whole `plugins/`+`shared/` tree for `uv run ... external_review.py`
  invocation blocks and assert `--project` on every one found, with a
  total-count sanity assertion (`EXPECTED_TOTAL_BLOCKS = 9`) so a scan that
  silently finds nothing fails loudly instead of passing vacuously.
  Confirmed by grep this adds no false positives from the ~15 historical/
  prose mentions of the script elsewhere in the repo (`.shipwright/`,
  `docs/`, `CHANGELOG.md`) — none of those are inside a `uv run` line.
- Two more test functions assert the producer/consumer sides of the new
  `plan_plugin_root` contract are real, not just documented: the runner's
  Input declaration, and `campaign-mode.md`'s spawn brief actually naming
  it (finding 3).
- A fourth asserts the canonical `{plan_plugin_root}` resolution +
  `uv run`-failure-handling note (finding 1, high severity) exists, so
  every other call site's pointer to it resolves to something real.
- Existing `test_sub_iterate_runner_contract.py` (37 tests) re-run to
  confirm the new Input parameter doesn't break the runner contract's
  other drift-protection assertions.
- Manual `uv run --project` probes against a no-`pyproject.toml` scratch
  directory, reproducing then fixing the actual reported failure — run
  against BOTH the monorepo copy and the installed plugin-cache copy
  (finding 6) — this repo's own root `pyproject.toml` declares `openai`
  too, so a monorepo-only check would prove nothing (per the card's
  explicit correction).
- No E2E/browser layer, but the CLI probes above ARE the surface —
  Verification reclassified `none` → `cli` (finding 10), evidence being
  the pytest run plus the probe transcripts in the iterate spec's
  Confidence Calibration.

## 6. Alternative approach (rejected)
**Alternative:** Hardcode `--project "{repo_root}/plugins/shipwright-plan"`
(the literal monorepo path the card's original draft proposed) at each
call site instead of threading `{plan_plugin_root}`.

**Rejected because:** that path does not exist in a consumer project,
where plugins run from `~/.claude/plugins/cache/shipwright/shipwright-plan/<version>/`,
not from a `plugins/` subdirectory of the target repo. Hardcoding it would
fix only the monorepo (which was never broken — its root `pyproject.toml`
already resolves `openai`) and leave every actual consumer broken, which
is the opposite of the fix's purpose. `{plan_plugin_root}` is already the
placeholder 4 of the 6 sites use for `--plugin-root`, and the same runtime
resolution mechanism generalizes to `--project` without inventing a new
one.
