# Iterate Spec — SS8: single-session is the default (deprecate multi-session)

- **Run ID:** `iterate-2026-07-08-ss8-default-single-session`
- **Campaign:** `2026-07-07-single-session-pipeline` · sub-iterate **SS8** (closing act)
- **Intent:** CHANGE · **Complexity:** medium · **Spec Impact:** none (no product FR
  added/modified/removed; framework-infra default change). FR-gate: `change_type: infra`.
- **Anchor:** campaign `trg-9d973f4f`

## Goal

Make `single_session` the default and sole supported `/shipwright-run` pipeline
mode; deprecate `multi_session` (code retained, removal deferred to `trg-0e8e7f90`).
Decision: `Spec/pipeline-as-campaign-convergence.md` §SUPERSEDING-DECISION (one
user, no back-compat).

## The crux — separate the fresh default from the legacy fallback

`DEFAULT_RUN_MODE` was overloaded (fresh-run default AND mode-less/unrecognized
read fallback). Flipping it wholesale would silently reinterpret an existing
mode-less multi-session run as single-session mid-flight. So:
- `DEFAULT_RUN_MODE = "single_session"` — fresh runs (`cli.py --mode` default,
  `config_factory`).
- NEW `LEGACY_FALLBACK_MODE = "multi_session"` — `config_io.run_mode` for
  mode-less/unrecognized configs (UNCHANGED — existing runs migrate EXPLICITLY).
- `single_session_loop.py` `wrong_mode` message uses the legacy fallback too.

## Changes

- Source: `constants.py` (flip default + add `LEGACY_FALLBACK_MODE`), `config_io.py`
  (fallback → new constant), `single_session_loop.py` (wrong_mode message),
  `cli.py` + `config_factory.py` (help/docstring prose).
- Schema: `run_config.v2.schema.json` default → single_session + description.
- Runtime prompts: `/shipwright-run` SKILL.md Step 3/4 (single default, multi
  deprecated), `references/single-session-loop.md`, `shared/prompts/single-session-gate-discipline.md`.
- Docs: `docs/hooks-and-pipeline.md`; NEW `docs/migrations/multi-session-to-single-session.md`.
- Tests: `test_run_config_mode.py` (flip default expectations + separation test),
  `test_run_skill_mode_selection.py` (single default + deprecated), and made
  explicit-multi_session: `test_single_session_loop.py`, `test_single_session_resume.py`,
  `test_single_session_backcompat.py`, `integration-tests/test_cross_surface_backcompat.py`.

## Confidence Calibration

- **Boundaries touched:** the `run_config.mode` default (fresh vs legacy-read),
  the write-config CLI, the run SKILL mode-selection, the v2 schema.
- **Empirical probes run:** 75 shipwright-run mode/loop/resume/backcompat/cli tests
  PASS; full `integration-tests/` 184 PASS under the flipped default (multi-session
  lifecycle is mode-agnostic, so nothing broke); migration path re-verified earlier
  (flip + resume, both boundaries). ruff clean; SKILL.md at 400 (budget).
- **Test Completeness Ledger:** below — every behavior `tested`; 0 untested-testable.
- **Confidence-pattern check:** asymptote = the real CLI/schema/SKILL drive the
  assertions; breadth = fresh-default + legacy-fallback-separation + schema + CLI +
  SKILL + multi-session-untouched + migration doc. No `cross_component` (no
  merge/hook/validator machinery touched).

### Test Completeness Ledger (finalize at F5)

| Behavior | Disposition | Evidence |
|---|---|---|
| Fresh config (no --mode) defaults to single_session | tested | `test_create_config_default_mode_is_single_session` + `…cli_defaults_mode_single_session` |
| Fresh default and mode-less read fallback deliberately diverge | tested | `test_fresh_default_and_legacy_fallback_deliberately_diverge` |
| Mode-less/unrecognized config still reads as multi_session | tested | `test_run_mode_defaults_missing_to_multi_session`, `…coerces_unknown…` |
| Schema `mode.default` == single_session | tested | `test_schema_declares_optional_mode_with_default` |
| A multi_session config still resolves `wrong_mode` in the single-session loop | tested | `test_resolve_wrong_mode_on_multi_session` |
| Deprecated multi_session lifecycle untouched (no single-session leak) | tested | `test_single_session_backcompat.py` suite |
| SKILL Step-3 marks single_session default + multi_session deprecated | tested | `test_skill_marks_single_session_default` |
| In-flight multi_session run still resumable (migration substrate) | tested | `integration-tests/test_cross_surface_backcompat.py` |
| Migration guide exists | tested | `docs/migrations/multi-session-to-single-session.md` present |
| Green CI under the new default | tested | F0 full run |

## Out of scope

- Removing the multi-session code path (deferred → `trg-0e8e7f90`).
- The WebUI single-session representation (new campaign `trg-01db884a`, shipwright-webui).
- `gate_policy.py`'s own `DEFAULT_RUN_MODE` (its legacy fallback stays multi_session — correct/safe).
