# Step 9 — Completion

**Verification (all must pass before "phase complete"):**

Gates 5–8 are one command. Run it and fix what it names — do not eyeball them:

```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/check-plan-gates.py \
  --planning-dir "{planning_dir}" --gate sections
```

Non-zero exit = STOP. The same four gates run again inside `_validate_plan`
below, so skipping this only defers the failure to a worse moment.

1. plan.md exists with SECTION_MANIFEST
2. All declared sections have files
3. Interview transcript exists
4. E2E test plan exists (if enabled)
5. **Section Quality Gate** — each section file says what it is for
   (`## Overview`), lists **at least 2** implementation steps
   (`## Implementation Steps`), and states how it will be tested
   (`## Tests First`).
6. **FR Coverage Check** — every live requirement in the split's `spec.md` is
   named by at least one section's `Requirements:` line. An uncovered
   requirement → assign it to a section, or add one.
7. **Section Trace Check** — every section names at least one live requirement
   it serves. A section that serves none is work nobody asked for: remove it,
   or find the requirement it belongs to.
8. **Dependency Order** — every dependency a section declares in
   `SECTION_MANIFEST` must appear **earlier** in the manifest than the section
   naming it. Declaration format: [section-index.md](section-index.md).
   `check-sections.py` (Step 7) fails this too.

Gates 5–7 are *lenient in the verifier* toward splits written before these
formats existed (they warn instead of failing), but `check-plan-gates.py` is
strict: a plan written now complies.

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
# section id validity, the four Step-9 gates above, canon, phase_history)
# — missing artifacts or drift blocks this call via ask-level issues.
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
