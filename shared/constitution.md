# Shipwright Constitution

> Governing principles for all Shipwright agents and subagents.
> This document is the single source of truth for behavioral boundaries.
> Hooks enforce some rules programmatically — this document covers all rules declaratively.

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
- Log decisions that deviate from spec in `agent_docs/decision_log.md`
- Update compliance incrementally after each pipeline phase
- Keep files under 300 lines — split if larger
- Fix the code, not the test — never weaken assertions to make tests pass
- Diagnose test failures before skipping — attempt autonomous fix (e.g., restart services, seed data, fix config), escalate to user if fix fails after 2 attempts
- Verify after non-trivial edits — run `tsc --noEmit` (TypeScript) or project linter before reporting success
- Re-read files before editing in long sessions (10+ messages) — do not trust cached content after auto-compaction
- State explicitly when search results may be truncated — never silently work with incomplete data

## ASK FIRST (require user confirmation)

- Destructive database operations (`DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `DELETE FROM` without WHERE)
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
| Smoke test | Pipeline stops (blocking) | App not running = can't deploy |
| E2E tests | Warning only (non-blocking) | Can be flaky; log but continue |

## Programmatic Enforcement

These rules are also enforced by hooks (see `docs/hooks-and-pipeline.md`):

| Hook | Enforces |
|---|---|
| `validate_command.sh` | Blocks rm -rf, push --force to main, DROP DATABASE |
| `check_secrets.sh` | Scans for API keys, tokens, passwords in written files |
| `check_destructive_migration.sh` | Warns on DROP/DELETE in .sql without down.sql |
| `check_file_size.py` | Warns if file exceeds size limit |

The constitution documents the complete set of rules. Hooks provide a programmatic safety net for the most critical subset.
