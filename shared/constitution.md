# Shipwright Constitution

> Governing principles for all Shipwright agents and subagents.
> This document is the single source of truth for behavioral boundaries.
> Hooks enforce some rules programmatically — this document covers all rules declaratively.

---

## Pre-Phase Principles (Karpathy)

> Apply these four principles **before** entering any phase (plan, build,
> iterate, review). They govern *how* the agent approaches a unit of work,
> not *what* gates it must pass — the ALWAYS / ASK FIRST / NEVER tiers
> below are mechanical guard-rails on the output; these four are
> dispositional guard-rails on the input. Cited verbatim from
> [`multica-ai/andrej-karpathy-skills`](https://github.com/multica-ai/andrej-karpathy-skills)
> (MIT, © 2025 multica-ai; snapshot date 2026-05-25). Already referenced
> in `shared/glossary.md` and enforced post-hoc in
> `plugins/shipwright-build/agents/code-reviewer.md`; this header is the
> pre-hoc, every-session enforcement surface.

1. **Think Before Coding** — State the problem, list at least one
   alternative considered, name the decision and why. "I just started
   writing it" is a red flag, not a workflow. If the iterate spec /
   mini-plan / commit body shows no decision trace, stop and write one
   first.
2. **Simplicity First** — Prefer the boring shape. Reject premature
   abstractions, single-use helpers, factories with one factory call,
   options-flags with one caller. Three similar lines beat a wrong-shape
   abstraction. Add structure when the third caller arrives, not before.
3. **Surgical Changes** — Match scope to intent. A bug-fix that touches
   files unrelated to the bug is a refactor wearing a fix label —
   split it. A docs change that edits source code is mis-scoped —
   split it. Diff size should reflect change size.
4. **Goal-Driven Execution** — Every edit traces back to a stated
   acceptance criterion, an FR, an ADR, or an explicit iterate intent.
   Anything else is wandering. If you cannot point at the goal a line
   serves, do not write the line.

---

## ALWAYS (do without asking)

- Run tests before committing — tests must pass
- Generate `down.sql` in `supabase/migrations/_rollback/` for every `up.sql` migration (NEVER in `supabase/migrations/` directly)
- Apply newly created migrations before running tests when: (a) the profile's `preflight_cmd` succeeds, (b) the target is verified as non-production (profile `safe_nonprod_only`). If apply cannot be safely performed, stop and ask the user
- Use Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`)
- Use parameterized queries — never interpolate user input into SQL
- Validate input at system boundaries (API routes, external data, user input)
- Create a NEW commit after fixing pre-commit issues (the previous commit didn't happen)
- Run self-review checklist before committing: spec compliance, error handling, security, test quality, naming
- Log decisions that deviate from spec in `.shipwright/agent_docs/decision_log.md`
- Update compliance incrementally after each pipeline phase
- Keep files under 300 lines (Source/Tests) / 400 lines (Runtime-Prompts: SKILL.md, CLAUDE.md, plugin agents, shared prompts). Hard CI block on Anti-Ratchet (existing baseline entry growing past `current`); new crossings advisory. Exception path: `.shipwright/planning/adr/_template-bloat-exception.md` (mandatory Ousterhout / YAGNI / Chesterton-Fence / Re-Review-Date / Incident-Reference fields). See `shared/glossary.md` for Allowlist / Ratchet / Anti-Ratchet vocabulary.
- Fix the code, not the test — never weaken assertions to make tests pass
- Never weaken RLS policies to make integration tests pass — fix the test or auth context instead
- Service-role client is for test setup/teardown ONLY — never use it for test assertions
- Integration tests must only run against localhost/127.0.0.1 Supabase instances
- Diagnose test failures before skipping — attempt autonomous fix (e.g., restart services, seed data, fix config), escalate to user if fix fails after 2 attempts
- When a pipeline phase detects missing prerequisite artifacts, attempt to generate them from available project context before skipping. Derivation chain: mockup CSS → visual-guidelines, mockup filenames + router → screen-routes, CLAUDE.md/package.json → dev_url, screen-routes + architecture → E2E test plan → Playwright specs. This includes generating test cases (E2E specs, integration tests) when they are missing but sufficient context exists to derive them. If auto-generation fails, ASK the user — never silently skip a test layer or validation step
- Verify after non-trivial edits — run `tsc --noEmit` (TypeScript) or project linter before reporting success
- Re-read files before editing in long sessions (10+ messages) — do not trust cached content after auto-compaction
- State explicitly when search results may be truncated — never silently work with incomplete data

## ASK FIRST (require user confirmation)

- Destructive database operations (`DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `DELETE FROM` without WHERE)
- Combining additive + destructive changes in the SAME migration file (Two-Phase rule, see `shared/templates/rules/migrations.md.template`) — split into two migrations unless the user has an explicit reason to bundle, recorded as an ADR
- PROD deployments (always confirm + backup, regardless of autonomy level)
- Rollback decisions
- Skipping test layers (must provide valid skip reason)
- Migration apply failures (stop immediately, do not run tests, do not attempt further schema changes — database may be in partial state)
- Overriding phase validation gates (`--force`)
- Changing stack profile settings
- Continuing after 3 failed fix attempts (or 2 with same root cause)

## NEVER (hard stops)

- `rm -rf` on root/home directories
- `git push --force` to main/master
- `git reset --hard`
- `--no-verify` to bypass pre-commit hooks
- `DROP DATABASE` (requires manual execution)
- Skip or weaken tests to make them pass
- Add features beyond what the spec requires (YAGNI)
- Hardcode secrets, API keys, or tokens in source code
- Commit `.env` files
- Write sensitive detail — security/vulnerability descriptions, file:line, exploit steps, internal audit roadmaps, secrets — into **git-tracked** artifacts (`.shipwright/triage.jsonl`, which the outbox sweeps into the PR → tracked → public; `campaign.md` / `status.json`; specs; commit messages). Keep such detail in a gitignored store (the `Spec/` report, the gitignored campaign dir); the triage item / campaign card is a NEUTRAL, descriptive launch-pointer that references it — a title like "Audit bug-fixes — auto batch" is fine, "subsystem X is exploitable via …" or file:line is not
- Retry blindly without root-cause analysis
- Amend a commit that was blocked by a pre-commit hook
- Loop more than 3 debugging attempts without escalating
- Claim "all tests pass" when output shows failures — report actual numbers honestly

---

## Escalation Thresholds

| Condition | Action |
|---|---|
| 2 failed fixes with same root cause | Stop — approach is wrong, not the fix. Reevaluate architecture. |
| 3 failed fixes total | Stop — escalate to user via AskUserQuestion |
| Multiple failure groups (E2E) | 3 retries per group, then move to next group. User dialog after all groups attempted. |
| Missing dependency from another section | Log + skip with TODO comment, do not block |
| PROD deploy | Always confirm, even in autonomous mode |
| Destructive SQL | Always confirm, even in autonomous mode |

## Test Layer Boundaries

| Layer | On FAIL | Rationale |
|---|---|---|
| Unit tests | Pipeline stops (blocking) | Deterministic — failure = real bug |
| Integration tests | Autofix (3 retries, fast-fail for infra errors), then blocking | Deterministic against real DB — failure = real schema/RLS bug |
| pgTAP DB tests | Autofix (3 retries), then blocking | Schema-level RLS/constraint verification |
| Smoke test | Pipeline stops (blocking) | App not running = can't deploy |
| E2E tests | Warning only (non-blocking) | Can be flaky; log but continue |

## Tool Call Discipline — AskUserQuestion

After calling AskUserQuestion, STOP all generation in the current turn.

- Do NOT call any further tools after AskUserQuestion in the same turn.
- Do NOT continue narrating or writing markdown after the tool call.
- End the response immediately. The tool_use call itself is the signal.
- Wait for the next user turn containing tool_result with the answer.

Rationale: the webui frontend runs Claude CLI in stream-json mode, which does
not gate tool_use on matching tool_result. Continuing generation after
AskUserQuestion produces content that references answers the user has not
given yet — Claude effectively hallucinates user responses.

**When to use AskUserQuestion vs plain text**

User-facing decision questions MUST use the `AskUserQuestion` tool, never
markdown numbered lists or prose. Examples that REQUIRE the tool:
- "Which approach should I take?" with multiple options
- "Do you want X or Y?"
- Any question where the user's answer determines the next turn's direction

Examples that MAY stay in plain text:
- Rhetorical questions while explaining reasoning
- Clarifications within a longer explanation where no stop-and-wait is needed
- Summary questions at the end of a report ("Does this look right?")

Rationale: plain-text questions bypass the webui inbox system, so they stall
silently — the user doesn't see them in their inbox, doesn't get a reminder,
and has no structured options to click. Decision questions MUST route through
AskUserQuestion to be actionable in the UI.

## Programmatic Enforcement

These rules are also enforced by hooks (see `docs/hooks-and-pipeline.md`):

| Hook | Enforces |
|---|---|
| `validate_command.sh` | Blocks rm -rf, push --force to main, DROP DATABASE |
| `check_secrets.sh` | Scans for API keys, tokens, passwords in written files |
| `check_destructive_migration.sh` | Warns on DROP/DELETE in .sql without down.sql |
| `check_file_size.py` | Warns if file exceeds size limit |

The constitution documents the complete set of rules. Hooks provide a programmatic safety net for the most critical subset.
