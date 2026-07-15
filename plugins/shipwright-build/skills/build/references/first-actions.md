# First Actions — Detailed Reference

Detail for Kern "CRITICAL: First Actions" section. The Kern declares step letters A..G; this file holds the long-form procedures for D2 environment validation, D setup script JSON parsing, and the C2 mandatory context-loading list.

## C. Detect Invocation Mode

**The `phaseTaskId` the orchestrator hands you at dispatch is the authority** — NOT any
state field inside `shipwright_run_config.json`. The pipeline's v1 state fields are no
longer advanced, so keying on them made every driven phase past the first misclassify
itself as standalone; the rationale is in `shared/scripts/lib/phase_invocation_mode.py`.
**Never re-derive the mode yourself.** Ask the resolver:

```bash
uv run "{shared_root}/scripts/tools/get_phase_context.py" \
  --phase-task-id "{phaseTaskId}" --phase build --project-root "{project_root}"
```

Omit `--phase-task-id` if you were not handed one. Set `invocation_mode` from the returned
`mode`, which is exactly one of:

- **`pipeline`** — you were dispatched. Enforce gates, and do the phase's real work.
  **Do NOT call `orchestrator.py update-step`** (nor any other run-state write): in a
  driven run `single-session-apply` owns phase completion — it records your status when
  it applies your result. See `plugins/shipwright-run/skills/run/SKILL.md`. (`update-step`
  is inert in a driven run anyway, but do not rely on that.) Do NOT mark artifacts standalone. A per-split build
  carries its `splitId` in the same payload — the token identifies *which* build task you
  are, which a phase-scoped run-state field could never do.
- **`standalone`** — no token, so this is a hand-invoked run:
  - Skip pipeline state updates (no `orchestrator.py update-step` calls)
  - Skip upstream completion checks
  - Still produce all artifacts (`shipwright_build_config.json`, code, tests, commits)
  - **Mark artifacts**: when writing `shipwright_build_config.json`, add `"mode": "standalone"` at the top level.
  - Use simpler branch name: `build/{section-name}` instead of pipeline naming convention
  - Print: `"Running in standalone mode — pipeline state will not be updated."`
  - If `requires_out_of_sequence_warning` is `true`, a driven run is LIVE at
    `active_phases`. Warn that running `/shipwright-build` out-of-band may collide with it,
    and **ask the user before continuing** (gate `build.out-of-sequence-continue`).
- **`error`** (exit code 2) — you were dispatched but the token does not resolve (stale,
  terminal, wrong phase, or an unreadable config). **STOP.** Do NOT continue as
  standalone: that is precisely what stamps a driven run's artifacts `"mode": "standalone"`
  and deadlocks the pipeline. Surface it to the orchestrator as an `ok: false` result.

Store the resolver's verdict as `invocation_mode` — `"pipeline"` | `"standalone"` | `"error"` (STOP) — for use in later steps.

## D. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>` into your context.

**If `SHIPWRIGHT_PLUGIN_ROOT` is in your context**, use it directly.

**Only if NOT in context**, fall back to search:

```bash
find "$(pwd)" -name "setup_implementation_session.py" -path "*/shipwright-build/scripts/checks/*" -type f 2>/dev/null | head -1
```

## C2. Load Project Context (MANDATORY)

**Read these files NOW before proceeding.** This context ensures coding standards, past decisions, and app structure are known before implementation begins. Do NOT skip this step.

1. `CLAUDE.md` — stack, conventions, commands
2. `.shipwright/agent_docs/conventions.md` — coding standards, naming, patterns
3. `.shipwright/agent_docs/decision_log.md` — ALL architectural decisions (read the complete file)
4. `.shipwright/agent_docs/architecture.md` — app structure, component tree, data flow
5. Run: `git log --oneline -10` — recent commits from other sections

If a file does not exist, skip it silently.

## D. Run Setup Script

```bash
uv run "{plugin_root}/scripts/checks/setup_implementation_session.py" \
  --file "{section_file_path}" \
  --plugin-root "{plugin_root}" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"
```

Parse the JSON output. Check for:

1. **`success == true`**: Proceed
2. **`mode == "resume"`**: Skip to `resume_from_step`
3. **`success == false`**: Report error and stop

## D2. Initialize & Validate Environment

Ensure `.env.local` exists with the required variable placeholders, then validate.

### D2a. Initialize .env.local

```bash
uv run "{shared_root}/scripts/validate_env.py" \
  --project-root "{project_root}" \
  --phase build \
  --init
```

Where `{shared_root}` = `{plugin_root}/../../shared` (relative to plugin root).

Parse the JSON output:

1. **`action == "created"`**: File was generated — inform the user:
   ```
   Created .env.local with placeholder variables from profile '{profile}'.
   Please fill in the values and remove the leading '#' to activate each variable.
   ```
2. **`action == "updated"`**: New vars were appended — inform the user:
   ```
   Updated .env.local — added missing variables: {added}.
   Please fill in the new values.
   ```
3. **`action == "unchanged"` or `action == "skipped"`**: Proceed silently.

### D2b. Validate Environment

```bash
uv run "{shared_root}/scripts/validate_env.py" \
  --project-root "{project_root}" \
  --phase build
```

Parse the JSON output:

1. **`skipped == true`**: No profile configured or no vars defined — continue with a note:
   ```
   Env validation skipped: {skip_reason}
   ```

2. **`success == true`**: All required vars found — continue:
   ```
   Environment validated: {found_count} required vars present
   ```

3. **`success == false`**: Missing required vars — **use AskUserQuestion** to inform the user:

   Ask the user with a message like:
   > **Missing environment variables for build**
   >
   > The following required variables are not set in `.env.local` or your environment:
   > - `VAR_NAME` — description
   >
   > `.env.local` has been created/updated with placeholders — fill in the values and remove the leading `#`.

   Options: "I've updated the file — continue" / "Skip validation and proceed anyway"

   If user updates: **re-run the validation script** to confirm.
   If user skips: proceed with a warning logged.

4. **`optional_missing`** (non-empty): Log a warning but do not block:
   ```
   Optional vars not set: VAR_NAME (description). Some features may not work.
   ```

## E. Create Feature Branch

**Always create a feature branch before making changes.**

The setup script (Step D) returns `branch_name` in its JSON output. The create path must anchor the new branch on the project's default branch (not whatever HEAD happens to be — ad-hoc `/shipwright-build --from <section>` can be invoked from any branch). The resume path is unchanged:

```bash
if git show-ref --quiet refs/heads/{branch_name}; then
  # Resume path — unchanged
  git checkout {branch_name}
else
  # Create path — anchor on default branch for deterministic base
  DEFAULT_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' || echo main)
  git checkout "$DEFAULT_BRANCH"
  git checkout -b {branch_name}
fi
```

Branch naming pattern: `build/{project-slug}-{session-id}` (e.g., `build/my-app-20260411-120000`).
Fallback without run config: `build/{session-id}`. Fallback without session-id: `build/{section-name}`.

For parallel build runs on different sections, the same worktree conventions from `/shipwright-iterate` B1a apply (branch from default, `.worktrees/<slug>` inside repo, disjoint file scopes). The pipeline default (sequential builds) is not affected.

## F. Load Config

Read `shipwright_build_config.json` from the project root (if exists).

Defaults:

```json
{
  "auto_push": false,
  "conventional_commits": true,
  "decision_log": true,
  "session_handoff": true,
  "migration_safety": true
}
```

## G. Print Session Report

```
================================================================================
SESSION REPORT
================================================================================
Mode:           {new | resume}
Section:        {section_name}
Branch:         {branch_name}
Auto-push:      {enabled | disabled}
Migration safe: {enabled | disabled}
{Resume from:   Step {N} (if resuming)}
================================================================================
```

---

## Single-Session Gate Discipline

When this phase runs as a phase-runner subagent under the **single-session
pipeline** (`shipwright_run_config.json` `mode: "single_session"`), interactive
`AskUserQuestion` gates follow a per-gate policy instead of always stopping.
Resolve each gate before you stop on it:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/resolve_gate_policy.py" \
  --phase build --list --project-root .
```

Apply the printed `effective_policy`:

- `auto-default` → proceed with the `default_answer`, **no END-TURN** (e.g.
  code-review findings auto-fix, as in autonomous mode).
- `orchestrator-approve` / `hard-stop` → **STILL STOP** and hand a gate-pending
  result back to the orchestrator; never auto-answer. Note:
  `build.destructive-sql-confirm` and `build.migration-apply-fail` are
  **hard-stop** — an explicit human decision, always, regardless of autonomy.
- `interactive` (any non-single-session run) → behave exactly as documented.

Full contract: `shared/prompts/single-session-gate-discipline.md`.
