# Mini-Plan: git-side-coverage-hook
- **run_id:** iterate-2026-10-09-git-side-coverage-hook

## Files
- NEW `plugins/shipwright-compliance/scripts/hooks/git_precommit_rtm_coverage.py` — git-side entrypoint (stdlib, `uv run --no-project`); reuses `rtm_gate_support.measure/read_threshold/meets`, `compliance_override.try_release/instruction/notice`; fail-open wrapper.
- NEW `plugins/shipwright-compliance/scripts/lib/git_side_release.py` — `grant(root, hook)` / `take(root, hook, now)` hand-off token (`O_EXCL` create, `unlink` = single winner, TTL 10 min, sweep).
- EDIT `plugins/shipwright-compliance/scripts/hooks/check_rtm_coverage.py` — on an override release call `git_side_release.grant`; docstring names the second enforcement point.
- EDIT `scripts/hooks/pre-commit` — run anti-ratchet, then the coverage check; keep each one's skip rules; non-zero if either failed.
- NEW tests `plugins/shipwright-compliance/tests/test_git_precommit_rtm_coverage.py` (+ token unit tests).
- EDIT `docs/hooks-and-pipeline.md` (hooks registry, `check_rtm_coverage in detail`, hand-off), `CLAUDE.md` pre-commit paragraph, CHANGELOG drop, decision drop.

## Work breakdown
1. Token module + unit tests (grant/take once, expiry, concurrent single winner).
2. Git-side script + tests AC-1,2,3,4,5 (temp repos, real `git commit`).
3. Override path AC-6 and hand-off AC-7 (PreToolUse grant ↔ git take).
4. Wire `pre-commit` AC-8; AC-9 shapes the lexer misses.
5. Docs + changelog + decision drop.

## Test strategy
Subprocess tests against real temp git repos (hermetic env helpers from `rtm_hook_test_support`), installing a copy of the real `scripts/hooks/pre-commit` plus the worktree's script. One `integration` behavior: real `git commit` → pre-commit → script → measure → override log.

## Alternative approach (rejected)
Keep extending the lexer one shape at a time — rejected: unbounded; the U13 architecture review set the stopping rule "over-fire instead of more grammar", and a parse-free check at the real commit closes the class. A Claude-side `PostToolUse` check — rejected: runs after the commit already exists.
