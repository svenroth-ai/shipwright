# Iterate Spec: git-side-coverage-hook

- **Run ID:** iterate-2026-10-09-git-side-coverage-hook
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
The commit-time coverage gate (`check_rtm_coverage`) decides from the Bash command text, so every shell shape its lexer cannot read is a commit it never sees (open shapes after `iterate-2026-10-08-u13-hook-command-shapes`: ANSI-C quoting, `<<` inside `${…}`, leading redirections, unknown git global options, wrappers such as `uv run`/`stdbuf`/`flock`/`setsid`). Add a second check that fires **at the real commit, run by git itself** (`pre-commit`), so the class is closed instead of one shape at a time. It measures the manifest **as staged for this very commit** (git hands the hook the real index, including `-a`/pathspec commits), which also removes the PreToolUse hook's documented "ordering limit".

## Acceptance Criteria
- [ ] AC-1 (blocks below threshold): in a temp git repo whose staged `test-traceability.json` covers 1 of 2 active requirements (threshold 0.8), `git commit` through the installed `pre-commit` exits non-zero, writes `BLOCKED (check_rtm_coverage, git pre-commit)` with the measured figure to stderr, and creates no commit.
- [ ] AC-2 (allows at/above threshold): with 2 of 2 covered the same commit succeeds and the output carries the one-line figure.
- [ ] AC-3 (measures what is committed): a manifest staged by the same `git commit -a` / `git commit <pathspec>` (below threshold in the index while above in HEAD, and the reverse) is judged on the staged copy.
- [ ] AC-4 (no data / unmeasurable): a repo with no compliance data commits (exit 0, no WARN - `measure` produces none); a non-current schema or a manifest with no executed result commits (exit 0) with the specific `measure` WARN on stderr - never a silent block.
- [ ] AC-5 (fail-open): an internal error (measurement raising) exits 0 with a visible `WARN … NOT evaluating` on stderr; the deliberate block is exit code 3 and ONLY that blocks - a script that crashes, fails to parse, or exits any other non-zero (uv/interpreter failure) is a WARN + allow in `pre-commit`.
- [ ] AC-6 (override): after one logged `check_rtm_coverage | OVERRIDE` line, the blocked git-side commit passes once with a visible WARN and writes the `CONSUMED` line + marker (same `compliance_override.try_release`); a second commit is blocked again.
- [ ] AC-7 (no double override): when the PreToolUse hook released a command through an override, the git-side check of that same command passes without a second logged override (a 2-minute untracked hand-off token bound to the HEAD it was granted on and to the consumed override entry it rides on (a hand-written token without a consumed override is refused), removed by EVERY git-side run and honoured by at most one; an expired, absent or HEAD-mismatched token means normal evaluation - so the second commit of `a && b` needs its own override).
- [ ] AC-8 (wired): `scripts/hooks/pre-commit` runs the coverage check after the anti-ratchet check (both always run; blocked if either blocks), no early exit skips the second step when the bloat baseline is absent; `uv` missing: anti-ratchet blocks as before, coverage prints a WARN and does not run; coverage script missing: WARN.
- [ ] AC-9 (a shape the lexer misses is caught): a commit through `uv run … git commit`, a `stdbuf` wrapper, or ANSI-C-quoted `git $'commit'` — for which `is_git_commit` returns False — is blocked by the git-side check when below threshold.

## Spec Impact
- **Classification:** none
- **ADD:** none · **MODIFY:** none · **REMOVE:** none
- **NONE justification:** adds a second enforcement point for the existing commit-time coverage gate (FR-01.10); requirement text and thresholds do not change. Affected FR: FR-01.10.

## Out of Scope
- Consumer projects: `core.hooksPath` is set only in the Shipwright monorepo by `scripts/install-hooks.sh`; installing the same check into adopted/generated projects is a separate decision (recorded as a follow-up).
- `git commit --no-verify` (forbidden by the constitution; the PreToolUse hook and CI remain the other two enforcement points).
- Extending the lexer with more shapes (the stopping rule of the U13 architecture review).
- Merge / rebase commits that do not run `pre-commit`.

## Design Notes
n/a (no UI).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| PreToolUse `check_rtm_coverage` on an override release (`.shipwright/locks/git-side-release-<hook>`, untracked) | git-side check `take()` | file holding the granting HEAD sha (`none` if unborn), mtime = grant time, TTL 2 min, removed by every git-side run |
| git (hook env: `GIT_INDEX_FILE`, cwd = worktree root) | `rtm_gate_support.measure` via `manifest_cov.read_manifest_noted` (`git show :<path>` else HEAD) | staged manifest JSON |
| `scripts/hooks/pre-commit` | git | exit code |

## Confidence Calibration
- **Boundaries touched:** the three rows above.
- **Empirical probes run:** real `git init` temp repos with `core.hooksPath` pointing at a copy of the real `pre-commit`; real `git commit` invocations (AC-1..9).
- **Test Completeness Ledger:** filled at F5.
- **Confidence-pattern check:** every AC maps to ≥1 end-to-end test; integration behavior: git → hook → measure → override log composes (category `integration`).

## Verification (medium+)
- **Surface:** none
- **Justification (surface=none):** internal git hook with no web/API/CLI surface of its own; exercised end-to-end by subprocess tests that run real `git commit` in temp repos with the real hook installed.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** right design; weak points were fail-open at the shell boundary, an unbound hand-off token and unspecified root/AC wording.
- **Findings:** (1) uv/interpreter failure would block, high - fixed (exit code 3 is the only block; other non-zero = WARN+allow); (2) `run_failopen` is silent - fixed (own try/except printing the WARN; wrapper not used); (3) token unbound/lingering, high - fixed (bound to HEAD, taken on every run, TTL 2 min), residual disclosed; (4) override unit mismatch (`a && b`) - disclosed and documented; (5) project root under hook-inherited env, medium - fixed (git toplevel, `SHIPWRIGHT_PROJECT_ROOT` ignored); (6) unattended subprocess committers gated, medium - disclosed (measured 100% >= 70% on this repo today; a below-threshold manifest now blocks them like any commit); (7) threshold config read from the working tree, medium - disclosed; (8) AC-8 contradiction, medium - fixed (matrix in AC-8, no early exit); (9) cp1252 stderr turning a release into a crash, medium - fixed (UTF-8 reconfigure) + test; (10) test-harness footguns - fixed (hermetic env, positive-output assertions); (11) AC-4 wording - fixed; (12) CONSUMED line lands in the next commit - documented; (13) two `uv run` per commit - accepted.
- **Known limitations:** a token whose commit never reached git is honoured by a below-threshold commit on the same HEAD for up to 2 minutes; the config threshold is read from the working tree; merges/amends that run `pre-commit` are judged like any commit.
- **Status:** 9 fixed, 4 disclosed, 0 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** build B; the smallest variant would drop the hand-off token.
- **Findings:** (1) record that the lexer gets no new shapes - fixed (stopping rule in the hook docstring and docs); (2) step-aside variant removes the token - declined-with-reason: it would drop the earlier PreToolUse block and needs per-target-repo "installed" detection, which is more machinery than the token; (3) token not bound - fixed (HEAD-bound, every-run take); (4) behaviour when hooks are not installed - disclosed (PreToolUse stays the enforcer, then CI); (5) shared measurement drift - accepted, one read path.
- **Known limitations:** clones without `install-hooks.sh` have only the PreToolUse hook and CI.
- **Status:** 2 fixed, 2 disclosed, 1 declined

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-10-09-git-side-coverage-hook/architecture_brief.md`
- **Verdicts:** glm=approve - openai=reject
- **Smallest thing that would do (per reviewers):** glm: B as proposed; openai: C (keep the PreToolUse check, no more lexer work, rely on CI and the F11 verifier).
- **Findings:** openai (proportionality, medium): a late red CI is recoverable, so a second local gate plus a hand-off is not warranted; glm (low): the token is the one piece that could shrink - kept small, no renewal logic.
- **Reconciliation:** the request for this run names the git-side check as the intended fix and calls the lexer treadmill the problem; the openai reject is option C, which the brief itself marks survivable and the request already weighed (not urgent, CI checks coverage again). Under --autonomous there is no operator to ask, so the plan stands with this reason recorded and the rejection is surfaced in the F12 summary. The token stays minimal.

## External Plan Review (glm, openai)
- **Verdicts:** glm=revise - openai=revise
- **Findings:** hand-off token unbound / races - fixed (HEAD-bound, every-run take); index-only measurement (a staged deletion of the manifest falls back to HEAD's copy) - disclosed: `measure` is shared with the PreToolUse hook and deleting the manifest is not a coverage-raising move; merge/amend/docs-only commits - disclosed (same gate as the PreToolUse hook); token generation race (read-old/regrant) - disclosed, bounded by the 2-minute TTL and the same trust class as the override; silent degradation when uv is absent - fixed to a visible WARN, canary-in-CI declined (out of scope).
