# Review dispositions (B7)

## Architecture review: openai reject OVERRIDDEN
glm approve, internal architecture reviewer approve, openai reject (prefers a manual procedure). Overridden by the orchestrator on the operator's behalf: scope fixed by the approved BRIEF rev 4 section 3 B7 and the unit spec; the reviewer was not given that context. Recorded in the ADR.

## External-Plan-Review-Findings (glm approve, openai revise)
| Finding | Disposition |
|---|---|
| Pending-prompt signal for the idle abort (both) | accepted-and-fixed: inbox page checked at idle abort, outcome recorded |
| Stale login copies after a hard kill (glm) | accepted-and-fixed: scrubbed at startup, only copies older than the budget |
| One idempotent shutdown path (openai) | accepted-and-fixed: Shutdown class, report also written from it |
| Build step own timeout and report entry (glm) | accepted-and-fixed |
| Sanitize CLAUDE_CONFIG_DIR / APPDATA (glm) | accepted-and-fixed: childEnv + unit test |
| Copy mockups into the report folder (glm) | rejected-with-reason: orchestrator scoped it out; follow-up list in the ADR |
| Env-file malformed-line behaviour, fixture completeness, other low items | rejected-with-reason: parser skips malformed lines; fixture validated by pytest; not core path |

## Internal arms
architecture-internal-reviewer: approve. opus-plan-reviewer: approve with changes; accepted-and-fixed: .claude.json key tail removed at shutdown, credential exposure documented in README, killServer declared before use, 300-line and no-defaults pytest already present. Skipped: record WebUI commit (follow-up).

## External-Code-Review-Findings (glm revise, openai revise)
| Finding | Disposition |
|---|---|
| No report on signal interruption (both) | accepted-and-fixed: report written from the shutdown path |
| Scrub could delete a concurrent run's login (glm) | accepted-and-fixed: only copies older than the budget plus 60 minutes |
| Budget clock starts after setup (both) | accepted-and-fixed: one deadline from run start; fetches bounded |
| H11 accepts pane null | accepted-and-fixed |
| H07 / H09 / H04 too loose | accepted-and-fixed in part: H04 per-mockup, H07 names the thread, H09 refusal/success wording; state read-back is a follow-up |
| checkProjectFiles untested | accepted-and-fixed: unit test |
| Idle abort broader than spec | rejected-with-reason: conservative; escalation text records prompt presence |
