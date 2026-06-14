# Mini-Plan — phase-quality rollups exclude sentinel-run snapshots

**run_id:** `iterate-2026-06-14-phasequality-sentinel-rollup-filter` · medium · CHANGE (spec-impact NONE)

## Chosen approach
Add one shared filter at the phase-quality **read/rollup layer** so degenerate
`run_id ∈ {"", "unknown"}` audit snapshots (audits that ran with no resolvable
run/session context) stop driving false Tier-1 surfacing.

1. `_constants.py` — `RUN_ID_SENTINELS` + `is_sentinel_run(run_id)`.
2. `_aggregates.py` — `LoadedFinding.is_sentinel` + `load_actionable_findings()`
   = `load_findings()` minus sentinel snapshots (order + fields preserved).
3. Route the 4 rollup consumers through `load_actionable_findings`:
   `collect_in_scope_fails` (triage backlog), and the 3 `_dashboard_render`
   rewrites (digest → SessionStart injection, dashboard, report).
4. `__init__.py` exports; `docs/hooks-and-pipeline.md` note.

Raw `load_findings` + `gc_old_findings` stay unchanged (JSONs remain on disk).

## Why this layer (not the alternatives)
- **Not the WRITE path** (`audit_phase_quality_on_stop.py`): that is a hook
  (`cross_component`) and would not retroactively neutralize the pre-fix /
  degenerate snapshots already on disk. The read-layer filter fixes both the
  stale backlog AND any future degenerate audit, with no hook touch.
- **Not a staleness/age window:** the discriminating property is the degenerate
  *run context* (sentinel), not age. A real-run FAIL stays real and is
  superseded by the next real audit; an age threshold would be arbitrary.
- **Not `load_findings` itself:** keep the raw enumerator honest for GC /
  forensics; filter only the actionable VIEWS.

## Risk / blast radius
Pure list reduction; sentinel run_id only arises with no session at all
(`resolve_run_id` → `session_id or "unknown"`), so no real-session finding is
hidden. 20 new tests (per-consumer + end-to-end backlog) + full `shared/tests`
regression green; `_triage_bundle.py` held at its 308 bloat baseline.
