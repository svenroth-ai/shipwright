# Step 8: Completion

**Goal:** Verify and summarize.

## Verification (all must pass before "phase complete")

1. All declared splits have spec.md files
2. project-manifest.md exists and lists all splits with execution order
3. CLAUDE.md and AGENTS.md exist (Full Application only). AGENTS.md's
   generation is agent-instruction-driven (project-scaffolding.md step 2),
   not a deterministic render call, so this is code-level gated rather
   than left to the prose alone: `check_agents_md_completion`
   (`shared/scripts/tools/verifiers/agents_md_completion_check.py`) is
   registered in the same `run_project_checks` dispatcher item 7 below
   uses, ERROR severity, and BLOCKS completion (via `single-session-apply`'s
   phase gate in a driven run, via the `update-step` call further down on a
   standalone run) unless AGENTS.md exists, contains the Codex appendix marker, AND its
   body before the appendix is CLAUDE.md's actual content with the three
   documented substitutions applied (not merely a file that happens to
   contain the marker somewhere — checked against
   `shared/scripts/lib/agents_md_substitutions.py`'s canonical pairs). It
   has no CLI of its own: it runs inside that dispatcher, i.e. in the
   apply-path phase gate of a driven run and in `update-step` otherwise.
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

   **Most of these checks are ERROR severity — the phase is not complete
   while one is red, and the code enforces it.** The same check is registered as
   `check_grill_trace_completeness` inside
   `shared/scripts/tools/verifiers/project_checks.py::run_project_checks()`
   — the SAME dispatcher C1-C5 use. In a driven run `single-session-apply`'s
   phase gate (enforcing by default) runs it through `validate_phase()` and
   rejects the result on red; on a standalone run the `update-step --step
   project` call at the end of this phase does (it is inert in a driven run).
   Running the CLI first surfaces the same gap earlier, in this turn.

   **ERROR severity (blocks completion):** at least one requirement's
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
   project phase complete while any of these is red.** Go back to the interview, resolve the
   named gap (grill the missing dimension, ask instead of assuming,
   sharpen the undefined term into `CONTEXT.md`, add the fit criterion, or
   write the missing requirement's trace), re-run the producer, and re-run
   this gate. It never judges prose quality — only structural completeness
   (`shared/grill-trace-format.md` §3) — so fixing a red result is always a
   completeness fix, never a rewrite for tone.

   **Every entry channel owes the same two artifacts** — the interview, a
   Brief package (`brief_project_mode.py apply`) and a seed file alike must
   leave `shipwright_project_interview.md` (a transcript, or the brief-mode
   pointer to the signed-off package) and one grill-trace per requirement.
   Also ERROR: `grill_trace_coverage` once spec.md FR rows exist (or the
   project config says `complete`) with no transcript and no traces — the
   interview was bypassed; `interview_transcript_present` — traces exist but
   the transcript/pointer does not; and `fr_trace_coverage` — a live FR row
   whose `Name` slug has no matching grill-trace (a partially recorded
   interview) — in Extension scope only rows whose Basis is not `interview`
   (inherited, adopted) downgrade to a WARNING; an untraced `interview` row still blocks. `human_signoff` — a brief-mode pointer
   or `brief:` trace without a `brief_dir` in run_config, or a `confirmed_by`
   naming no person (`agent`, `claude`, `auto`, `seed`). If `fr_trace_coverage` is a false positive (a renamed
   requirement), align the FR `Name` with the trace's `requirement_key`; do
   not skip the trace.

   **A project whose interview began before this gate shipped** will
   correctly show `grill_trace_coverage` red at Step 8 — the transcript
   exists but pre-dates the trace producer. That is not a false block: the
   evidence this gate exists to require genuinely was not captured.
   Remediate by writing a trace per already-confirmed requirement (a short
   retroactive pass, using the same producer) before completing the phase —
   there is no separate "grandfather" path, by design (the design's own
   thesis: a prompt-only guarantee that reads "should have happened" is
   exactly what this gate replaces). The same pre-existing-interview gap
   also surfaces as a blocking `fr_trace_coverage` result; the same
   retroactive pass resolves it.

## Phase complete — update pipeline state

Iterate 12.1 brings the project plugin to full Minimum Phase Completion
Canon (C1/C2/C3/C4/C5 + phase_history). C1/C2/C4 were already in place;
C3 (inline session_handoff) + C5 (CHANGELOG [Unreleased] entry) +
`phase_history` append are new. Execute the steps in the order shown:

```bash
# One run id for the C3 marker and phase_history (a driven run's id is kept):
: "${SHIPWRIGHT_RUN_ID:=project-$(date +%Y%m%d-%H%M%S)}"
export SHIPWRIGHT_RUN_ID

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
  --project-root "$(pwd)" --phase project --run-id "$SHIPWRIGHT_RUN_ID" \
  --entry-json '{"outcome":"scaffolded","splits":{N},"profile":"{profile}"}'

# Mark project phase complete (standalone run only; inert in a driven run).
# On a standalone run the phase validator runs the modular project_checks
# verifier -- if C1/C2/C3/C5, phase_history, OR the grill-trace
# completeness gate (P4.2) is red, this call blocks on an ask-level issue.
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step project --status complete
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

**The run id:** the first line keeps a `SHIPWRIGHT_RUN_ID` the caller already set (a
driven run exports the run's `runId`) and mints `project-<timestamp>` otherwise, so the C3
marker and the `phase_history` entry always carry a real id. A driven run's phase gate
accepts the id this phase recorded during its task (`docs/hooks-and-pipeline.md`).

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
{AGENTS.md: Generated (Full Application only)}
{.shipwright/agent_docs/: Generated (Full Application only)}

Next steps:
  1. Review project-manifest.md for execution order
  2. Run /shipwright-plan for each split:
     /shipwright-plan @01-name/spec.md
     /shipwright-plan @02-name/spec.md
     ...
================================================================================
```
