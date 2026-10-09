# Iterate Spec: u13-hook-command-shapes

- **Run ID:** iterate-2026-10-08-u13-hook-command-shapes
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
The commit-time coverage hook (`check_rtm_coverage`) and the override log shared with the security hook read more shell command shapes the way the shell does, so a real `git commit` is no longer hidden from the gate and one logged "Continue anyway" can no longer release more than one hook run. Follow-up to campaign `2026-10-07-finalization-claims-hardening` unit U13 (ADR `iterate-2026-10-08-u13-rtm-hook-followups-override-and-target`, sections "Doubt review" and "Accepted limits").

> **Process note (disclosed):** this run implemented first and ran the plan-stage reviews (internal plan, internal architecture, external plan + architecture) over the spec/mini-plan afterwards, together with the code cascade. The plan reviews therefore judge a plan whose implementation already exists; their findings are still integrated or dispositioned below.

## Acceptance Criteria
- [ ] AC-1 (heredoc order): `is_git_commit("cat <<E\\\nOF\ngit commit -m x\nEOF")` is False (a continuation-split delimiter is `EOF`, the body is data), while `is_git_commit("cat > a <<'EOF'\nC:\\dir\\\nEOF\ngit commit -m x\ncat > b <<'EOF'\ny\nEOF")` is True (a backslash ending a QUOTED body line is literal and does not swallow the closing `EOF`).
- [ ] AC-2 (odd/unclosed delimiters): a backslash-, quote- or `$`-bearing delimiter (`<<E\OF`, `<<EO"F"`, `<<E$X`) and a body whose delimiter line never comes leave the following `git commit` visible: `is_git_commit` is True for each.
- [ ] AC-3 (nested shells): `iter_git_commits("bash -c 'git -C a commit -m x; git -C b commit -m y'")` returns `[("-C","a"),("-C","b")]`; the same holds for `eval`, `pwsh -Command`, `cmd /c` and `env -S "bash -c '…'"`.
- [ ] AC-4 (substitutions): `is_git_commit` is True for `echo "$(git commit -m x)"`, `` echo `git commit -m x` ``, `diff <(git commit -m x) f` and `echo "$(( $(git commit -m x | wc -l) + 1 ))"`, and False for `echo '$(git commit -m x)'`, `echo "\$(git commit -m x)"` and `echo "$(git status)"`; 2000-deep nesting over-fires instead of raising.
- [ ] AC-5 (unparseable text): `is_git_commit("# Let's commit\ngit -C x commit -m y")` is True; `is_git_commit("echo don't; git status")` is False.
- [ ] AC-6 (shell cwd): `commit_scope("git commit -m x", <payload cwd = project B>, default=lambda: project A)` resolves to project B when B holds compliance data and `SHIPWRIGHT_PROJECT_ROOT` is unset or names B; it resolves to A when the payload cwd is a project with nothing to measure, outside any project, or when `SHIPWRIGHT_PROJECT_ROOT` names another project.
- [ ] AC-7 (stale lock): `_break_stale` on a lock younger than 30 s leaves it in place; on a stale lock exactly one of two concurrent breakers returns True; a stale lock that cannot be renamed makes `_locked` raise `TimeoutError` within `LOCK_WAIT_S` (no busy spin).
- [ ] AC-8 (one command per override): after `try_release` released an entry once, a second `try_release` for the same hook returns `(None, …)`; a command holding two commits is released whole by that one override (unit = one hook run = one Bash command), documented in `docs/hooks-and-pipeline.md`.
- [ ] AC-9 (restore-proof consumption): after `git restore` removes the CONSUMED line from the tracked log, `active_override` is still None (an `O_EXCL` marker under `.shipwright/locks/` records the use); when the marker cannot be created `try_release` returns `(None, "… NOT applied …")`; a lost marker race returns `(None, "… concurrent …")`; a log without a final newline is not glued onto.

- [ ] AC-10 (review-round shapes, over-fire): `is_git_commit` is True for a commit on the line after `echo hi # note` plus a trailing backslash (a comment is not continued), after `(( y = x <<EOF ))` (arithmetic shift, not a heredoc), for `bash -c -- 'git commit'`, and for `eval eval eval eval eval git -C x commit` / `cmd /c` ×5 `git.exe  commit` (the depth-cap fallback reads `git … commit`, not only the exact text `git commit`).
- [ ] AC-11 (fallback keeps the target): for text shlex rejects (a stray quote) `iter_git_commits("# Let's go\ngit -C ../b commit -m y")` yields `("-C", "../b")`, not `()`.
- [ ] AC-12 (lock ownership): a lock removed from under its holder and re-taken by another owner is not unlinked by the displaced holder; consumption markers older than `WINDOW + CLOCK_SKEW + 10 min` are swept; a read-only lock directory fails closed after LOCK_WAIT_S, without busy-spinning.
- [ ] AC-13 (both hooks): after one release by `check_security_scan` and a `git restore` of the tracked log, the same deploy command is blocked again; a shell directory dropped in favour of the default root (missing directory, or `SHIPWRIGHT_PROJECT_ROOT` naming another project) produces a WARN naming both.

## Spec Impact
- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** hardens how existing commit-hook machinery (FR-01.10, the commit-time requirement-coverage gate and its override) classifies command shapes and consumes its override; no requirement text or acceptance criterion of the FR changes. Affected FR: FR-01.10.

## Out of Scope
- Shell constructs the lexer still does not model, recorded as accepted limits in the ADR: a trailing backslash inside a `#` comment, a multi-line command substitution inside an unquoted heredoc body, an odd number of apostrophes in comments, a `case` pattern's `)` inside `$(…)`, `env -C`/`cd path && git commit` locations.
- Making the override a human gate (it stays after-the-fact attribution, per the U13 ADR).
- `check_security_scan` command detection (deploy patterns) - only its use of the shared override helper changes.

## Design Notes
n/a (no UI).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `compliance_override.consume` (CONSUMED line + `O_EXCL` marker), the block's printed `printf` OVERRIDE line | `compliance_override._unconsumed` in both hooks | pipe-delimited log line + empty marker file `consumed-<hook>-<ts>` |
| hook payload `cwd` (Claude Code) | `rtm_commit_scope.commit_scope` → shared `project_root.resolve_project_root(cwd=…)` | JSON field, native path string |
| command text of the Bash tool call | `shell_heredoc.strip_heredoc_bodies`, `shell_substitution.substitutions`, `git_commit_command.iter_git_commits` | shell source text |

## Confidence Calibration
- **Boundaries touched:** the three rows above.
- **Empirical probes run:** see the ledger; every AC is exercised by `tests/test_hook_command_shapes.py` against real strings and real temp directories (git repos for the shell-cwd case). Two independent Opus reviews (code + doubt) each found a regression in the first implementation (continuation join inside quoted bodies; busy-spin on an unrenameable stale lock); both are fixed and pinned by tests. The asymptote check is repeated after the re-review below.
- **Test Completeness Ledger:** filled at F5 (mirrors `iterate_latest.test_completeness`).
- **Confidence-pattern check:** depth - two review rounds each produced real findings, so one more probe round (the re-review) runs before F0; breadth - every AC maps to ≥1 tested behavior, 0 untested-testable.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes (after the build - see the process note)
- **Severity:** medium
- **Summary:** override consumption holds up; the lexer had two fail-open shapes and the shell-cwd rule treated `SHIPWRIGHT_PROJECT_ROOT` differently from the `-C` path.
- **Findings:** (1) comment + backslash continuation hides a commit, medium - fixed (`_ends_in_comment`); (2) `(( … <<EOF ))` read as a heredoc, medium - fixed (`((` arithmetic context); (3) depth-cap fallbacks used the exact text `git commit`, low - fixed (`_LOOSE_COMMIT` everywhere); (4) `bash -c -- 'cmd'` - fixed; `powershell git commit`, `bash --rcfile f -c`, `pwsh -EncodedCommand` - disclosed; (5) env var vs `-C` precedence and silent fallbacks, medium - fixed (one rule: shell project only with compliance data and no conflicting env; every drop is a WARN); (6) missing-directory WARN - fixed; (7) marker weaknesses: no cleanup - fixed (sweep); same-second entries share a marker - disclosed (fails closed); consumer repos whose `.gitignore` predates `.shipwright/locks/` - disclosed; (8) lock edge cases: PermissionError retry and the lock path in the message - fixed; (9) no hook-level restore test for `check_security_scan` - fixed (AC-13); (10) missing AC-4 cases (`>(…)`, CRLF, depth cap) - added; (11) lexer growth - disclosed (see Known limitations).
- **Known limitations:** `powershell <positional>`, `bash --rcfile f -c`, `pwsh -EncodedCommand`; `$[ … ]` arithmetic; a consumer `.gitignore` without `.shipwright/locks/`; two OVERRIDE entries in the same second share one marker; the hand-written lexer keeps a list of accepted limits (ADR) - each new gap is evidence for eventually adding a parse-free git-side backstop.
- **Status:** 9 fixed, 4 disclosed, 0 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes (after the build)
- **Severity:** medium
- **Summary:** build option A (extend the lexer + marker); D breaks "never hide a commit", B violates stdlib-only.
- **Findings:** (1) option C (git-side hook) as a backstop - disclosed: it can be skipped with `--no-verify` and needs per-clone installation, planned as a follow-up if the limit list keeps growing; stopping rule adopted: new shapes are handled by over-firing, not by more grammar; (2) `cd path && git commit` / `env -C` still judged on the starting directory - disclosed (listed accepted limit; the card scopes them out); (3) marker called a correctness fix, not a security one, and swept - fixed; (4) markers are per worktree (the tracked log is too), separate clones out of scope - disclosed; (5) this review ran after the build - recorded in the decision drop.
- **Known limitations:** as above.
- **Status:** 2 fixed, 3 disclosed, 0 declined

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-10-08-u13-hook-command-shapes/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed (extend the lexer; one untracked marker per consumed override).
- **Findings:** marker directory has no retention - accepted-and-fixed (sweep); option C backstop - accepted as a recorded follow-up; one override per command is the right rule - kept and stated plainly in the docs.
- **Reconciliation:** the plan had rejected a real shell parser (stdlib-only hook; PowerShell/`cmd` forms remain) and a lock-only override design (no mutual exclusion once broken; append order not atomic on Windows); both reviewers agree.

## External Plan Review (glm, openai)
- **Verdicts:** glm=revise · openai=revise (no contradiction).
- **Findings:** lock ownership after a rename - accepted-and-fixed (ownership token, only the owner unlinks); fallback must preserve the commit's location - accepted-and-fixed (`_LOOSE_OPTS`, AC-11); marker accumulation - accepted-and-fixed (sweep); marker bound to a timestamp rather than an entry hash - rejected-with-reason: two entries in one second are consumed together by design (fail-closed, documented since the U13 ADR #8) and a hash would not change the CONSUMED-line match; state the release unit plainly - accepted-and-fixed (docs); name the fallback's comment over-fire as accepted - accepted; env-names-C/cwd-B/no-location three-way test - accepted-and-fixed; assert the failure path waits - accepted-and-fixed.

## Verification (medium+)
- **Surface:** none
- **Runner command:** n/a
- **Evidence path:** n/a
- **Justification (only if surface=none):** the change is internal Python library code of a PreToolUse hook with no startable web/API/CLI surface of its own; it is exercised end-to-end by the existing hook subprocess tests (`test_rtm_coverage_hook_committed.py`, `test_compliance_override.py`) which run the real hook script against real temp repos.
