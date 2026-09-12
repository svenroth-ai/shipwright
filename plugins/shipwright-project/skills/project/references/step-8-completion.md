# Step 8: Completion

**Goal:** Verify and summarize.

## Verification (all must pass before "phase complete")

1. All declared splits have spec.md files
2. project-manifest.md exists and lists all splits with execution order
3. CLAUDE.md exists (Full Application only)
4. .shipwright/agent_docs/ directory exists with all 3 files — architecture.md,
   decision_log.md, conventions.md (Full Application only; session_handoff.md
   is written later by the Stop hook, not scaffolded here, and does not count
   toward this check)
5. **Spec Completeness Gate** — for each spec.md, verify it contains:
   - Scope section (what's included / excluded)
   - Functional Requirements (at least 1 FR with ID, e.g., FR-01.01)
   - Non-Functional Requirements section
   - If any spec.md is missing these sections → fix before proceeding
6. **Manifest-Spec Consistency** — no split in manifest without spec.md, no spec.md without split in manifest
7. **Grill-Trace Completeness Gate (P4.2, `shared/grill-trace-format.md`)** —
   run the completeness gate over every grill-trace record this interview
   wrote (see interview-protocol.md → "Capturing the grill-trace"):

   ```bash
   uv run "{shared_root}/scripts/tools/verify_grill_trace_completeness.py" \
     --project-root "$(pwd)"
   ```

   **Most of these checks BLOCK phase completion at the code level — not
   advisory, and not something the agent decides on its own.** The same
   check is registered as `check_grill_trace_completeness` inside
   `shared/scripts/tools/verifiers/project_checks.py::run_project_checks()`
   — the SAME dispatcher C1-C5 use — so the orchestrator's `update-step
   --step project` call at the end of this phase (below) genuinely re-runs
   it via `phase_validators.validate_phase()` and refuses completion on a
   red result from any of the checks below marked ERROR, exactly like a
   missing C1/C4/C5 artifact does today. Running the CLI here first is a
   convenience — it surfaces the same failing trace/dimension earlier, in
   this turn, instead of discovering it only when `update-step` blocks.

   **ERROR severity (blocks `update-step`):** at least one requirement's
   grill-trace is missing entirely (an interview ran but nothing was
   written — `grill_trace_coverage`), a trace has a blank dimension,
   carries an `assumed` value (this surface permits no exceptions),
   declares a term that resolves in neither `shared/glossary.md` nor
   `CONTEXT.md`, answers `outcome` with no `fit_criterion`,
   `shared/glossary.md` itself is missing (`glossary_source_available`), a
   term the trace recorded sharpening was never listed in `terms_used`
   (`glossary_delta_declared`), or the trace file itself (or the target
   project's `CONTEXT.md`) is malformed and could not be parsed
   (`malformed_trace` / `malformed_context`). **Do not attempt to mark the
   project phase complete while any of these is red — the `update-step`
   call will be blocked anyway.** Go back to the interview, resolve the
   named gap (grill the missing dimension, ask instead of assuming,
   sharpen the undefined term into `CONTEXT.md`, add the fit criterion, or
   write the missing requirement's trace), re-run the producer, and re-run
   this gate. It never judges prose quality — only structural completeness
   (`shared/grill-trace-format.md` §3) — so fixing a red result is always a
   completeness fix, never a rewrite for tone.

   **WARNING severity (visible, does not block `update-step`):**
   `fr_trace_coverage` — once spec.md files exist, a live FR row whose
   `Name` cell has no matching grill-trace at all (catches a partially
   recorded interview, not just a fully skipped one). This is routed to an
   `inform`-level note rather than an `ask`-level block
   (`phase_validators._run_canon_checks`, PR #705 Tier-3 review) because the
   FR-row-to-trace join has no stable identity contract yet (see
   `shared/grill-trace-format.md` §5 "Known limitation") — a mismatch here
   is still a real, worth-reading signal that the interview may have missed
   a requirement, so treat a red `fr_trace_coverage` result as a prompt to
   go back and check, just not as something that stops you from completing
   the phase.

   **A project whose interview began before this gate shipped** will
   correctly show `grill_trace_coverage` red at Step 8 — the transcript
   exists but pre-dates the trace producer. That is not a false block: the
   evidence this gate exists to require genuinely was not captured.
   Remediate by writing a trace per already-confirmed requirement (a short
   retroactive pass, using the same producer) before completing the phase —
   there is no separate "grandfather" path, by design (the design's own
   thesis: a prompt-only guarantee that reads "should have happened" is
   exactly what this gate replaces). The same pre-existing-interview gap
   can also surface as a `fr_trace_coverage` warning; because that check is
   WARNING severity it will not block completion, but it is still worth the
   same retroactive pass.

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
# verifier — if C1/C2/C3/C5, phase_history, OR the grill-trace
# completeness gate (P4.2) is red, this call blocks on an ask-level
# issue rather than silently advancing.
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
