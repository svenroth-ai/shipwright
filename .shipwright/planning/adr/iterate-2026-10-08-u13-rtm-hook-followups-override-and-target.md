# Compliance soft-block override and commit-target measurement

Run: `iterate-2026-10-08-u13-rtm-hook-followups` (campaign `2026-10-07-finalization-claims-hardening`, unit U13; closes the U9 follow-up triage card). Requirement: FR-01.10.

## Operator decisions (2026-10-08, binding)

1. **Partial test runs are "not measured".** An active requirement whose every linked test (its own and its ACs') is `not_run` in the evidence run leaves the coverage figure and is reported as `WARN: N of M requirements not measured`; never counted as covered or uncovered. A requirement with no linked test stays uncovered; a manifest with nothing executed stays unmeasurable.
2. **Override: logged and time-limited.** An entry `<UTC ts> | <hook> | OVERRIDE | <reason>` in `.shipwright/agent_docs/compliance_overrides.log` allows the hook's next blocked command within 30 minutes. Implemented as **single use**: the hook appends `<ts> | <hook> | CONSUMED | <entry ts>`; when that line cannot be written the override is not applied. Same helper (`lib/compliance_override.py`) for `check_rtm_coverage` and `check_security_scan`; the block names the exact `printf` line.

## What changed

- `rtm_manifest_coverage.compute_coverage`: `fr.not_measured`; AC inventory tracks FR heading depth (a sub-heading keeps its ACs; a heading at the FR's level or higher ends the section).
- `git_commit_command`: heredoc bodies stripped first (`lib/shell_heredoc.py`; an operator inside quotes or a `#` comment starts nothing; an unquoted-delimiter body line holding `$(`/backtick is kept); `git.cmd` like `git.exe`; `iter_git_commits` returns each commit's global options.
- `lib/git_commit_target.py`: `-C` in order, `--work-tree`, `--git-dir` (relative to the dir reached, MSYS `/c/` on Windows); a plain `-C` is resolved to its project (see the review fixes below). `rtm_commit_scope.commit_scope` judges a multi-repo line on the first repo below threshold and WARNs; `GIT_DIR`/`GIT_WORK_TREE` are scoped around the measurement (`git_env`).
- Both hooks print the block to stderr (the security hook printed stdout JSON only).

## PR review fixes (PR #847)

- **Project resolution is the shared resolver.** A plain `-C` is resolved by `shared/scripts/lib/project_root.resolve_project_root(allow_env=False, cwd=<reached dir>)` (new `cwd` keyword; steps 2-4), loaded by file under a sentinel module name (ADR-045). `git -C <markerless repo root> commit` and `git -C . commit` descend into the single project subdirectory again; a stray `.shipwright/` (no `.shipwright/agent_docs`, no config marker) no longer captures the target. Resolving to no project while the default root holds compliance data is a visible WARN, never a silent allow.
- **`--work-tree` alone** measures the index of the repo git finds from the reached directory (`GIT_DIR` from `git rev-parse --absolute-git-dir`), in the new `lib/rtm_commit_scope.py` (which also caches each repo's measurement on a multi-repo line).
- **Heredocs:** a body fed to a shell or interpreter (`bash sh zsh dash ksh pwsh powershell eval ssh`, or `-s`, anywhere in the operator's pipeline) is scanned as commands; a delimiter must start with a letter or `_`; `<<` inside `$((...))` is a shift; quote state carries across lines.
- **Measurement:** no active requirement measured is never a figure (N-of-M WARN + NOT evaluating); `execution_problem` counts only active requirements; `meets()` runs inside the hook's WARN guard, so a raising comparison WARNs.
- **Override:** read -> check -> append under an `O_EXCL` lock beside the log (stale after 30 s, re-read once held), via `compliance_override.try_release` in both hooks; a matching entry outside its window or future-dated is named in the block; the printed `printf` line `shlex.quote`s the reason and says how to escape a single quote; a line with more than one repo below threshold is never released by an override.
- **Attribution, not a human gate.** The operator chose "Freigabe im Protokoll" (approval in the log). The model can write the OVERRIDE line itself; the log gives after-the-fact attribution of who released which block and why, not proof that a human approved. The log is git-tracked, so OVERRIDE / CONSUMED lines may ride along with `git commit -a`. `.shipwright/compliance/compliance_overrides.log` (the Sec2 verifier's input) is a different path, not read by these hooks.

## Architecture Review

Verdicts: GLM `approve`, OpenAI `revise`. Brief offered A (30-minute window, any number of passes), B (single use), C (audit-only log), D (do nothing). OpenAI: B with the 30-minute expiry, since A authorizes more than "the next commit". GLM: A, calling single use extra persistent state. **Taken: B + 30-minute expiry** - it is the literal operator decision and consumption is one appended line in the existing append-only log, not a new store. GLM's other point (the log is now gate input, not only an audit trail) is documented in `docs/hooks-and-pipeline.md`.

## External-Plan-Review-Findings

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | OpenAI | high | 30-minute window exceeds "next commit" | accepted-and-fixed: single use + 30 min |
| 2 | OpenAI | high | Only the first commit target measured; cwd fallback | accepted-and-fixed: every target judged, first failing one decides; a missing directory WARNs (git itself fails that commit) |
| 3 | OpenAI | medium | Keeping a `$(` heredoc line can over-fire | rejected-with-reason: the over-fire needs a body line that itself starts with `git commit`; over-firing is the safe direction |
| 4 | OpenAI | low | Decision drop + triage card not in plan | accepted: this ADR + PR body |
| 5 | GLM | medium | `--git-dir`-only lookup directory undefined | accepted: cwd reached is the work tree (git semantics), tested with a separated git dir |
| 6 | GLM | medium | printf quoting / control characters in reason | accepted-and-fixed: reason a separate `%s` arg, log path `shlex.quote`d, control chars stripped from the echo |
| 7 | GLM | low | Malformed log lines | accepted: skipped, tested |
| 8 | GLM | low | `compute_coverage` callers | checked: only `rtm_gate_support` |
| 9 | GLM | low | Unterminated heredoc | accepted: the rest is body (bash semantics), tested |
| 10 | GLM | low | Option parsing duplicated | already so: `git_commit_target` consumes `iter_git_commits` output |

## External-Code-Review-Findings

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | OpenAI | high | `-C repo/src` measures `repo/src` | accepted-and-fixed: walk up to the project within the repo |
| 2 | OpenAI | high | Multi-repo line passes on the first repo | accepted-and-fixed: judged on the first below threshold |
| 3 | OpenAI | medium | `# <<EOF` in a comment swallows a later commit | accepted-and-fixed + test |
| 4 | OpenAI | medium | Unwritable CONSUMED line still allows | accepted-and-fixed: block stands, the reason is printed |
| 5 | GLM | high | Override missing on the legacy RTM block | rejected-with-reason: the override check sits after both branches build the reason; a test now proves the legacy block is released once |
| 6 | GLM | low | Log path in double quotes | accepted-and-fixed: `shlex.quote` |
| 7 | GLM | medium | `env -S` / depth-cap commits lose `-C` | rejected-with-reason: exotic paths, documented as not covered; the commit still gates against the default root |
| 8 | GLM | low | CONSUMED matched by timestamp | accepted as limitation: two entries in the same second are consumed together |
| 9 | GLM | low | `os.environ` mutated globally | accepted-and-fixed: `git_env` context manager |
| 10 | GLM | low | Decision drop / triage card | accepted: this ADR + PR body |

## Self-Review

1. Spec Compliance - pass: all 7 items built with FR-01.10-tagged tests. 2. Error Handling - pass: unreadable log means no override; unwritable CONSUMED keeps the block; a missing target WARNs. 3. Security Basics - pass: control characters stripped, quoted log path, future-dated entries ignored. 4. Test Quality - pass: real git repos; negative probe (GIT_DIR hand-off off fails the git-dir test); bash round trip of the printed line. 5. Performance Basics - pass: extra reads only on a block or a multi-repo line. 6. Naming & Structure - pass: three small lib modules; all touched files < 300 lines. 7. Affected Boundaries - pass: override log producers (printf line, `override_logger`, `consume`) and consumer round-trip probed.

## Confidence Calibration

Boundary: the override log (human/agent-edited). Probes: plain, BOM, CRLF, non-ASCII and cp1252 reasons, empty reason, no trailing newline, padded pipes. **Finding:** a BOM dropped the first entry, so it was fixed (`utf-8-sig`) and a regression test added. Re-probe: clean. Second probe set (two entries then two uses, `override_logger` round trip, CONSUMED of a microsecond timestamp): clean, so the asymptote was reached. Boundary: command text. CRLF heredocs and a non-ASCII delimiter were probed; the non-ASCII delimiter is not stripped, so it over-fires (accepted, safe direction). Not probed: a log on a read-only filesystem (simulated in a test via a failing `consume`).

## Doubt review (orchestrator, final head): fixed and accepted limits

- **Fixed:** an OVERRIDE line whose timestamp overflows UTC conversion (year 1 / 9999 with an offset) crashed `try_release` outside the WARN guard and so allowed silently and unlimited; `_when` now rejects such a timestamp (tests).
- **Accepted limit:** heredoc stripping runs before backslash-newline joining and its delimiter parsing can differ from bash for exotic delimiters (`<<E\OF`, `<<EO"F"`), so a later real commit can be hidden; `source`/`.`/`fish` bodies are stripped. Follow-up: join continuations first, keep the body when the delimiter is odd or never closes.
- **Accepted limit:** `bash -c` / `eval` wrappers judge only the first inner commit target.
- **Accepted limit:** the stale-lock break is stat-then-unlink (needs a crashed holder plus a concurrent pair); one override releases one hook invocation, however many commits the command holds; a CONSUMED line lost to `git restore` revives the entry for the rest of its 30 minutes; a plain `git commit` is resolved from the hook process cwd, not the persisted shell cwd.
