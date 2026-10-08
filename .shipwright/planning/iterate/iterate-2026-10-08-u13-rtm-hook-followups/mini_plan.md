# Mini-plan: U13 - RTM hook follow-ups (carried over from U9)

## Problem
U9 made `check_rtm_coverage` measure requirement coverage. Its reviews left seven gaps: a partial test run counts requirements as uncovered; the "Continue anyway" override is logged but neither soft-block hook (`check_rtm_coverage`, `check_security_scan`) reads the log, so the next attempt blocks again; the gate measures the cwd, not the repo `git -C <path> commit` goes to; heredoc bodies are scanned for `git commit`; ACs under a sub-heading of an FR section drop out of the AC inventory; a legacy-path test checks stdout only; `git.cmd` is not recognised as git.

## Change
1. **Not measured** (operator decision): in `rtm_manifest_coverage.compute_coverage`, an active requirement whose every linked test (its own and its ACs') is `not_run` leaves both figures and is counted in `fr.not_measured`; `rtm_gate_support.measure` WARNs "N of M requirements not measured", `describe` appends "N more not measured". A requirement with no linked test stays uncovered; an all-`not_run` manifest stays unmeasurable.
2. **Override** (operator decision): new `lib/compliance_override.py` (one shared helper). `active_override(root, hook)` reads `.shipwright/agent_docs/compliance_overrides.log` (pipe shape `ts | hook | OVERRIDE | reason`, and the `override_logger` shape); an entry with a reason, dated no more than 30 min ago and no more than 1 min in the future, lets that hook through with a visible WARN. `instruction()` prints the exact `printf ... >> <log>` line. Both hooks print the block to stderr as well (the security hook printed only stdout JSON).
3. **Target repo**: `git_commit_command.find_git_commit` returns git's global options of the first commit; new `lib/git_commit_target.py` applies `-C` (in order), `--work-tree`, `--git-dir` (relative to the dir reached; MSYS `/c/` paths on Windows). `rtm_gate_support.target_root` returns the root plus a `GIT_DIR`/`GIT_WORK_TREE` env for a `--git-dir` commit; a non-directory WARNs and falls back.
4. **Heredocs**: new `lib/shell_heredoc.py` strips heredoc bodies before lexing; an operator inside quotes starts nothing; an unquoted-delimiter body line with `$(`/backtick is kept (the shell runs it).
5. **AC parser**: track the FR heading level; only a heading at the same or a higher level ends the section.
6. **Test gap**: the legacy-path block test asserts both streams (no staging hint; override advice on stderr), moved to the new test file.
7. **Parser**: `.cmd` suffix stripped like `.exe`; `command git` already a wrapper (now tested); aliases documented as not covered.

Docs: `docs/hooks-and-pipeline.md` rows for both hooks + the detail note; `docs/guide.md` override sentence.

## Alternative approach considered
Single-use override (consumed by the first command it lets through) - rejected because consuming needs the PreToolUse hook to write state before the command runs, and a commit that then fails (a pre-commit hook) would burn the override; the 30-minute window is bounded and stateless. Resolving the target with `git rev-parse --show-toplevel` - rejected because it returns the monorepo root for a subdirectory project, while `-C` already names the project dir.

## Tests
New `tests/test_rtm_hook_followups.py` and `tests/test_compliance_override.py`, real temp git repos where git is involved, all tagged `pytest.mark.covers("FR-01.10")`; existing helpers switched from `not_run` to `fail` where they meant "uncovered".
