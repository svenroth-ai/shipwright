# Mini-plan: u13-hook-command-shapes

- **Run ID:** iterate-2026-10-08-u13-hook-command-shapes
- **Spec:** `.shipwright/planning/iterate/iterate-2026-10-08-u13-hook-command-shapes.md`

## Files
Edit (all `plugins/shipwright-compliance/`): `scripts/lib/shell_heredoc.py`, `scripts/lib/git_commit_command.py`, `scripts/lib/git_commit_target.py` (adds `project_at`), `scripts/lib/rtm_commit_scope.py`, `scripts/lib/compliance_override.py`, `tests/test_rtm_hook_followups.py` (one case moved: an unclosed heredoc now fires). New: `scripts/lib/shell_substitution.py`, `tests/test_hook_command_shapes.py`. Docs: `docs/hooks-and-pipeline.md` (override note + artifact matrix row). Drop: `CHANGELOG-unreleased.d/Fixed/…_001.md`.

## Work breakdown
1. `shell_heredoc`: join backslash-newline continuations for non-body lines only; accept an operator only when the delimiter word is followed by whitespace or a shell metacharacter; keep a body visible when its delimiter never closes. Test: AC-1, AC-2.
2. `shell_substitution` (new, pure): top-level bodies of `$(…)`, backticks, `<(…)`/`>(…)`, arithmetic bodies scanned for nested substitutions; single quotes and backslash hide. `git_commit_command.iter_git_commits` parses each body again (depth-bounded, `RecursionError` over-fires). Test: AC-4.
3. `git_commit_command`: `_segment_commits` is a generator - every inner commit of `sh|bash|zsh|dash -c`, `eval`, `pwsh -Command`, `cmd /c`, `env -S`; unparseable-text fallback uses a loose `git … commit` regex. Test: AC-3, AC-5.
4. `rtm_commit_scope`: a commit naming no location is judged on the project the payload cwd belongs to (via the shared resolver), only if it holds compliance data and `SHIPWRIGHT_PROJECT_ROOT` does not name another project; else the default. Test: AC-6.
5. `compliance_override`: stale lock broken by atomic rename + re-check (put back a live one); loop honours the deadline when the break fails; consumption claimed by an `O_EXCL` per-entry marker under `.shipwright/locks/` (fail closed), CONSUMED line kept for attribution (newline-safe). Unit of release documented as one hook run. Test: AC-7, AC-8, AC-9.
6. Docs + changelog drop; ADR/decision drop at F3.

## Test strategy
New `tests/test_hook_command_shapes.py` (all `pytest.mark.covers("FR-01.10")`), real strings, real temp dirs/git repos; full compliance plugin suite + ruff + `verify_local.py` at F0. No E2E surface (spec Verification: none).

## Alternative approach (medium)
Wrap/replace the hand-written lexer with a real shell parser (e.g. `bashlex`) - not adopted: a new third-party dependency in a hook that must stay stdlib-only and fail-open, and its own gaps (PowerShell, `cmd /c`, `env -S`) would remain. For the consumed-once guarantee, a lock-only design (no marker) was the first implementation; an `O_EXCL` marker per entry is the single arbiter instead because the lock, once broken, gives no mutual exclusion and `O_APPEND` ordering is not guaranteed on Windows.
