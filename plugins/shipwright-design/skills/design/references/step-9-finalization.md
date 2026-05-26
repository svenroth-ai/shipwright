# Step 9 — Finalization (iterate 12.2 — Minimum Phase Completion Canon)

**Run this only after Step 8.5 Option A approves the design** (all screens
signed off, FR coverage satisfied, spec backflow complete). The design
plugin had zero finalization calls before iterate 12.2; this step brings
it to full canon coverage (C1/C2/C3/C5 + `phase_history`). **C4 is
skipped by design policy** — design is a transformation of an existing
spec, not a decision-taking phase.

Set `SHIPWRIGHT_RUN_ID` at the top of this step so the canon-marker
handoff (C3) and `phase_history` append share one run id. If the env
var is unset, `generate_session_handoff.py --canon-marker` logs a
stderr warning and writes the handoff without the marker (safe
degrade — the Stop hook then regenerates normally at turn end).

```bash
# If the orchestrator didn't already set it, derive one here:
export SHIPWRIGHT_RUN_ID="design-$(date +%Y%m%d-%H%M%S)"

# C1 — Record phase completion event (idempotent — skips if recorded).
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" --type phase_completed --phase design \
  --detail "{N} screens, {M} flows"

# C2 — Update delivery dashboard.
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase design --detail "{N} screens, {M} flows" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 — Canon-marked session handoff (iterate 12.1 conditional stop-hook skip).
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "$(pwd)" --canon-marker --phase design \
  --reason "design complete: {N} screens, {M} flows"

# C4 — SKIPPED by policy (design is not a decision-taking phase).

# C5 — Append CHANGELOG [Unreleased] entry via helper (Keep-a-Changelog,
# dedupe, atomic). Category "Added" — designs are user-visible artifacts.
uv run "{shared_root}/scripts/tools/append_changelog_entry.py" \
  --project-root "$(pwd)" \
  --category Added \
  --entry "Design: {N} screens + {M} flows added"

# phase_history — audit trail in shipwright_run_config.json::phase_history[design]
uv run "{shared_root}/scripts/tools/append_phase_history.py" \
  --project-root "$(pwd)" --phase design --run-id "{SHIPWRIGHT_RUN_ID}" \
  --entry-json '{"screens":{N},"flows":{M},"outcome":"approved"}'

# Mark design phase complete. _validate_design() now runs the modular
# design_checks verifier (manifest screens exist, FR coverage, canon,
# phase_history) — missing artifacts block this call via ask-level issues.
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step design --status complete
```

Where `{shared_root}` = `{plugin_root}/../../shared`.
