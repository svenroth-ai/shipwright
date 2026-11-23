# Release guard hook (P4b, second pass B2)

Run: `iterate-2026-11-23-p4b-release-guard-hook`. Campaign unit P4b of `dfp-pilot-changelog-p3-p8`. Complexity: classifier said large (operator-accepted, `complexity_override: operator-accepted-large`), declared medium.

## Decision

A PreToolUse hook (`Bash|PowerShell`) in `shipwright-changelog` denies `git push` of a tag or trunk, `gh pr merge` of the release PR and `gh release create` while a release is in progress and `.shipwright/runtime/release_state.json` does not name HEAD. Inert unless `release_run.json` (git directory) is fresh (< 48 h), for this project root, and `v<version>` is not on `origin`.

## Judgement calls recorded for the operator (stop 3)

- **D34**: "record for HEAD" accepts HEAD = the record's commit, or a descendant reached only through commits that touch the event files (the `record-event` commit follows `commit-and-tag`). Strict equality would block the flow the skill prescribes.
- **D35**: "in progress" ends when the tag is on `origin`; an `origin` that cannot be asked keeps the deny.
- **D36**: the matcher is a cooperative net; documented misses.

## Architecture Review

External (glm, openai): both `approve`; internal `architecture-internal-reviewer`: `approve` with two medium completeness notes (a leftover marker needs an end of life; a block needs a way out), both addressed (48 h limit + tag-on-origin; deny message names the next step; `SHIPWRIGHT_RELEASE_GUARD=off`). Smallest option is A; C (a `publish` subcommand) is a possible complement, not a replacement.

## External-Plan-Review-Findings

| Finding | Source | Disposition |
|---|---|---|
| ls-remote error must not allow | glm medium, openai high | accepted-and-fixed: an unreachable origin keeps the deny (test) |
| event-commit exception vs "record for HEAD" | openai high | rejected-with-reason: strict equality blocks the prescribed order (record-event commits after the tag); recorded as D34 for stop 3; the descent is checked commit by commit |
| 48 h expiry, tag-on-origin, off switch not in spec | openai high | rejected-with-reason: "active only while in progress" needs an end; 48 h is `release_runstate.MAX_AGE_HOURS`; the switch follows the other hooks |
| fixed trunk names | openai medium, glm low | rejected-with-reason: documented; `origin/HEAD` lookup is a follow-up |
| `git -C` / `gh --repo` alignment | openai medium | accepted-and-fixed: `-C`, `cd`, `-R/--repo` handled |
| fail-open hides a regression | glm medium | rejected-with-reason: required by the unit; garbled-payload tests cover the known shapes |
| command substitution / `sh -c` | glm low | rejected-with-reason: documented known miss |

## Internal-Plan-Review-Findings (opus-plan-reviewer)

| Finding | Disposition |
|---|---|
| PowerShell tool not matched (high) | accepted-and-fixed: matcher `Bash|PowerShell`, both tool names accepted, tests |
| `gh pr merge` held for every PR (medium) | accepted-and-fixed: only the release branch / PR URL / number, or no argument on the release branch |
| deny message tells the model to delete the state (medium) | accepted-and-fixed: asks the user first; test that env text in the command cannot lift the guard |
| ls-remote may prompt for a login (medium) | accepted-and-fixed: prompts off, 8 s timeout |
| HEAD vs explicit source ref (medium) | rejected-with-reason: documented limit in the registry row |
| `cd` not tracked, `gh -R`, `/c/` paths (medium) | accepted-and-fixed |
| substitution refspec, `push.followTags`, `gh release edit`, trunk list, unbalanced quote (low) | rejected-with-reason: documented known misses |

## External-Code-Review-Findings

| Finding | Source | Disposition |
|---|---|---|
| `cd` ignored | openai high | accepted-and-fixed |
| `--repo` supplies the remote | openai medium | accepted-and-fixed |
| aggregate diff accepts change-then-revert | openai medium | accepted-and-fixed: per-commit paths, merges refused (test) |
| version-shaped branch read as a tag | glm low | accepted-and-fixed: tag shape needs the `v` prefix (test) |
| test name claims fails-on-old | glm low | rejected-with-reason: the block tests fail without the hook; the inert test is the false-block test |
| LEARNINGS append | glm low | accepted-and-fixed: appended in this diff |

## Confidence Calibration

Boundary: producer `release_runstate.save` / `release_commit.write_state` to the hook (file round trip) probed with the real producers in `test_release_guard.py` and the integration case; consumer-side shapes probed: torn JSON, non-dict, wrong version, foreign project root, stale age. Probes run: 6 families, 2 found bugs (the PowerShell matcher, the revert history), both fixed and re-probed with no further finding. Not probed: a real Claude Code process delivering the payload (the payload shape `tool_name`, `tool_input.command`, `cwd` is the documented one and is used by the iterate hooks).
