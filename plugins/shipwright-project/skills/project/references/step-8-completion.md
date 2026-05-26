# Step 8: Completion

**Goal:** Verify and summarize.

## Verification (all must pass before "phase complete")

1. All declared splits have spec.md files
2. project-manifest.md exists and lists all splits with execution order
3. CLAUDE.md exists (Full Application only)
4. .shipwright/agent_docs/ directory exists with all 5 files (Full Application only)
5. **Spec Completeness Gate** — for each spec.md, verify it contains:
   - Scope section (what's included / excluded)
   - Functional Requirements (at least 1 FR with ID, e.g., FR-01.01)
   - Non-Functional Requirements section
   - If any spec.md is missing these sections → fix before proceeding
6. **Manifest-Spec Consistency** — no split in manifest without spec.md, no spec.md without split in manifest

## Phase complete — update pipeline state

Iterate 12.1 brings the project plugin to full Minimum Phase Completion
Canon (C1/C2/C3/C4/C5 + phase_history). C1/C2/C4 were already in place;
C3 (inline session_handoff) + C5 (CHANGELOG [Unreleased] entry) +
`phase_history` append are new. Execute the steps in the order shown:

```bash
# C1 — Record phase completion event (idempotent — skips if already recorded)
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" --type phase_completed --phase project \
  --detail "{N} splits created"

# C2 — Update delivery dashboard
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase project --detail "{N} splits created" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 (NEW 12.1) — Canon-marked session handoff. Requires SHIPWRIGHT_RUN_ID
# env var; without it the marker is dropped with a warning (safe degrade)
# and the Stop hook will regenerate a generic handoff at turn end.
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "$(pwd)" --canon-marker --phase project \
  --reason "project scaffolding complete: {scope}, {N} splits"

# C4 — already written in Step 7 via write_decision_log.py (ADR for
# the project decomposition decision). Nothing to do here.

# C5 (NEW 12.1) — append CHANGELOG [Unreleased] entry via helper
# (Keep-a-Changelog, dedupe, atomic). Category "Added" per canon policy.
uv run "{shared_root}/scripts/tools/append_changelog_entry.py" \
  --project-root "$(pwd)" \
  --category Added \
  --entry "Project initialized: {name} ({N} splits, profile {profile})"

# phase_history append (NEW 12.1) — audit trail entry in
# shipwright_run_config.json::phase_history[project].
uv run "{shared_root}/scripts/tools/append_phase_history.py" \
  --project-root "$(pwd)" --phase project --run-id "{SHIPWRIGHT_RUN_ID}" \
  --entry-json '{"outcome":"scaffolded","splits":{N},"profile":"{profile}"}'

# Mark project phase complete (triggers compliance update automatically).
# The orchestrator's phase validator now runs the modular project_checks
# verifier — if C1/C2/C3/C5 or phase_history is missing, this call blocks
# on an ask-level issue rather than silently advancing.
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step project --status complete
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

**What happens if SHIPWRIGHT_RUN_ID is unset:** the C3 handoff helper
logs a warning to stderr and writes the handoff without the canon
frontmatter; the Stop hook then regenerates it normally at turn end.
The `append_phase_history.py` call will still run (it just uses the
empty string as run_id, which the verifier's phase_history check
treats as "skipped"). You can set the env var explicitly at the top
of Step 8 if you want the full canon flow:

```bash
export SHIPWRIGHT_RUN_ID="project-$(date +%Y%m%d-%H%M%S)"
```

## Print Summary

```
================================================================================
SHIPWRIGHT-PROJECT COMPLETE
================================================================================
Scope:    {Full Application | Extension}
Profile:  {profile_name}
Created {N} split(s):
  - 01-name/spec.md
  - 02-name/spec.md
  ...

Project manifest: project-manifest.md
{CLAUDE.md: Generated (Full Application only)}
{.shipwright/agent_docs/: Generated (Full Application only)}

Next steps:
  1. Review project-manifest.md for execution order
  2. Run /shipwright-plan for each split:
     /shipwright-plan @01-name/spec.md
     /shipwright-plan @02-name/spec.md
     ...
================================================================================
```
