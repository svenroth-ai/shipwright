# Mini-plan: P4b release guard hook (B2)

Complexity: large by the keyword classifier (operator-accepted), declared medium; effective large after the diff re-check.

## Goal
A PreToolUse `Bash` hook in `shipwright-changelog` that denies `git push` of a tag or of the trunk, `gh pr merge` and `gh release create` while a release is in progress and its record for HEAD is missing.

## Design
- `scripts/hooks/release_guard_commands.py`: pure lexer. `shlex` non-POSIX (Windows backslash paths survive), heredoc bodies blanked, split on `&& || ; | &` and newlines, redirections cut. Returns `Action(kind, c_paths, all_refs, tags, refs)` for `git [-C p] push ...`, `gh pr merge`, `gh release create`.
- `scripts/hooks/release_guard.py`: decision. An action is outward only if it pushes a tag (`--tags`, `--follow-tags`, `refs/tags/..`, a version-shaped name or an existing tag) or the trunk (main, master, develop named; `--all`; no refspec or `HEAD` on a trunk branch), or is a merge/release call. Only then are state files read.
- In progress = `release_run.json` (git dir, `git rev-parse --git-path shipwright/release_run.json`) valid, schema 1, under 48 hours, `project_root` is the cwd or an ancestor of it.
- Record: `.shipwright/runtime/release_state.json`, same version, 40/64-hex commit; HEAD is that commit or descends from it through event-only commits (`shipwright_events.jsonl`, `.shipwright/events/drops/`), because `record-event` commits after `commit-and-tag`.
- If no valid record: `git ls-remote --tags origin v<version>`; tag present or ls-remote error means the release is over, allow. Else deny.
- Output: `permissionDecision: deny` JSON, exit 0 (iterate guard shape). Any exception: allow. `SHIPWRIGHT_RELEASE_GUARD=off`.

## Files
hooks.json (PreToolUse/Bash entry, `uv run --no-project`), the two scripts, `docs/hooks-and-pipeline.md` registry row, tests `test_release_guard_commands.py`, `test_release_guard.py`, `integration-tests/test_changelog_release_guard_hook.py`; LEARNINGS/FINDINGS notes.

## Tests
Parser table (forms from the full-run report, Windows paths, quoted text, heredoc, redirects); real git: block without record, allow with record, different commit blocks, other version blocks, event-commit descent, ordinary push never blocked, 48 h and tag-on-origin inertness, other project root, `-C`, off switch, garbled payloads, corrupt state; integration case reads state written by the real producers.

## Golden freeze
None expected (hooks.json and hook scripts are not frozen); `golden_lock.py --check` must exit 0 with no delta.
