# Step 9 — Completion

**Verification (all must pass before "phase complete"):**

1. plan.md exists with SECTION_MANIFEST
2. All declared sections have files
3. Interview transcript exists
4. E2E test plan exists (if enabled)
5. **Section Quality Gate** — for each section file, verify it contains:
   - Description (what the section implements)
   - Implementation Steps (at least 2 concrete steps)
   - Test Strategy (what tests to write)
   - If any section is missing these → fix before proceeding
6. **FR Coverage Check** — read the spec's Functional Requirements,
   verify every FR is assigned to at least one section. If uncovered
   FRs found → add them to appropriate section or create new section.
7. **Dependency Order** — sections with dependencies must come after
   their dependencies in SECTION_MANIFEST.

---

## Phase complete — update pipeline state

Iterate 12.2 brings the plan plugin to full Minimum Phase Completion
Canon (C1+C2+C3+C4 + `phase_history`). C1/C2/C4 were already in place;
C3 (canon-marker handoff) + `phase_history` append are new. **C5 is
skipped by policy** — plan is an internal decomposition artifact, not a
user-facing change (no CHANGELOG entry).

Set `SHIPWRIGHT_RUN_ID` at the top of this step so the C3 canon marker
and `phase_history` entry share one id. Missing env var → safe degrade
(stderr warning, no canon marker, Stop hook regenerates normally).

```bash
# If the orchestrator didn't already set it, derive one here:
export SHIPWRIGHT_RUN_ID="plan-$(date +%Y%m%d-%H%M%S)-{split_name}"

# Update plan config to complete
uv run "{plugin_root}/scripts/checks/write-plan-config.py" \
  --project-root "$(pwd)" --status complete --split "{split_name}" --sections {N}

# C1 — Record phase completion event (idempotent — skips if recorded).
# --split-id makes a multi-split plan phase record one end PER split (dedup key
# is (phase, splitId)); aligns this SKILL emit with the orchestrator's per-split
# end so they collapse rather than leaving a phantom split-less plan end.
# (iterate-2026-07-11-phase-completed-per-split)
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" --type phase_completed --phase plan \
  --split-id "{split_name}" \
  --detail "{N} sections for {split_name}"

# C2 — Update delivery dashboard.
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase plan --detail "{N} sections for {split_name}" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 (NEW 12.2) — Canon-marked session handoff.
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "$(pwd)" --canon-marker --phase plan \
  --reason "plan complete: {split_name}, {N} sections"

# C4 — already written in Step 2 / Step 5 via write_decision_log.py
# (interview + external review decision ADRs). Nothing to do here.

# C5 — SKIPPED by policy (plan is internal decomposition, not user-facing).

# phase_history (NEW 12.2) — audit trail entry.
uv run "{shared_root}/scripts/tools/append_phase_history.py" \
  --project-root "$(pwd)" --phase plan --run-id "{SHIPWRIGHT_RUN_ID}" \
  --entry-json '{"split":"{split_name}","sections":{N},"outcome":"sectioned"}'

# Mark plan phase complete. _validate_plan() now runs the modular
# plan_checks verifier (plan_config status, section files, FR orphans,
# section id validity, canon, phase_history) — missing artifacts or
# drift blocks this call via ask-level issues.
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step plan --status complete
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

---

## Print Summary

```
================================================================================
SHIPWRIGHT-PLAN COMPLETE
================================================================================
Plan:         {planning_dir}/plan.md
Sections:     {N} sections generated
Review:       {external via OpenRouter/Gemini/OpenAI | self-review fallback (user opt-out) | self-review fallback (config opt-out)}
E2E Plan:     {generated | skipped}

Section files:
  - sections/01-name.md
  - sections/02-name.md
  ...

Next steps:
  1. Review plan.md and section files
  2. Run /shipwright-build for each section:
     /shipwright-build @sections/01-name.md
     /shipwright-build @sections/02-name.md
     ...
================================================================================
```
