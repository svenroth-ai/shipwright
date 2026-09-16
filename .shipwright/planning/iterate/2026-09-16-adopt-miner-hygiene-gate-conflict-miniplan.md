# Mini-Plan: adopt-miner-hygiene-gate-conflict

Run ID: iterate-2026-09-16-adopt-miner-hygiene-gate-conflict
Full spec: `.shipwright/planning/iterate/2026-09-16-adopt-miner-hygiene-gate-conflict.md`

## Problem

`plugins/shipwright-adopt/scripts/lib/test_acceptance_miner.py` mines raw
`describe`/`it`/`test_*` labels from a target repo's own test files into
`spec.md` acceptance-criteria bullets. Those labels routinely carry code
symbols (PascalCase component names in `describe(...)`) or HTTP verb+path
text, which trip `fr_hygiene_detectors.violations()` — the same detector
FR-01.02 #5 (`_project_gate_extras_rollout.criteria_free_of_implementation_
detail`) uses as a HARD block on `/shipwright-project` Step 8. The gate never
fires during adopt itself (adopt writes `status: complete` directly, bypassing
`update-step`/`run_project_checks`), so the conflict is dormant until a later
`/shipwright-project` Step 8 re-verifies the whole `spec.md`, including old
mined content, with no rollout-transition grace available for onboardings
after 2026-09-12T06:23:06Z (`trg-ac2ef362`).

## Alternatives considered

- **A (chosen): producer-side filtering.** Miner drops/reshapes dirty
  bullets, reusing `fr_hygiene_detectors.violations()` directly (shared
  vocabulary, no drift risk).
- **B (rejected, see spec's Architecture Review): gate-side permanent
  grace** for miner-sourced content — would be a standing, per-producer
  carve-out in a check whose whole point is universal applicability; rejected
  on the same reasoning the `trg-9583d3a8` precedent already used to reject
  an analogous permanent `scope == "extension"` skip for the same gate.

## Diff shape

1. `plugins/shipwright-adopt/scripts/lib/test_acceptance_miner.py`:
   - Import `fr_hygiene_detectors` via the plugin's existing collision-safe
     `shared_loader.load_shared_module` idiom (mirrors
     `gitleaks_config_scaffolder.py`'s precedent), never a naive `from lib
     import ...` (would collide with the plugin's own `lib` package,
     ADR-044/045).
   - `_mine_js`: after building `combined = f"{innermost}: {it_label}" if
     innermost else it_label`, keep `combined` if clean; else, if there was a
     prefix and `it_label` alone is clean, keep `it_label`; else drop the
     bullet.
   - `_mine_py`: after computing the candidate string (docstring first line
     or humanized name), keep it only if clean; else drop.
   - No change to cap logic — `_AC_CAP` truncation already happens after
     `_mine_js`/`_mine_py` return, so filtering upstream of that is free.
2. `plugins/shipwright-adopt/tests/test_test_acceptance_miner.py`: add cases
   per the spec's Test Completeness Ledger (10 new tests) — clean-kept,
   prefix-stripped, both-dirty-dropped, for both JS and Python shapes, plus a
   cap-interaction test.
3. No change to any gate-side file (`fr_hygiene_detectors.py`,
   `_project_gate_extras_rollout.py`, `_project_gate_wiring.py`,
   `_project_gate_rollout*.py`, `_project_gate_grace.py`).
4. Triage: `trg-ac2ef362` closed with `--task-ref PR:<N>` once this run's PR
   exists (follow-up append, same as the `trg-9583d3a8`/`trg-aedcfe7b`
   precedent's own closure mechanics).

## Risk / blast radius

Small and contained: one plugin-private helper file + its own test file.
Zero change to shared gate logic, zero change to any wire format
(`RolloutSnapshot`, `GateResult`, `CheckResult`), zero change to any other
plugin. The only observable behavior change is that `/shipwright-adopt`
onboarding runs after this ships produce spec.md acceptance-criteria bullets
that are a strict subset of today's (dirty ones removed/reshaped) — never a
new bullet, never a bullet's meaning changed, only some removed or shortened.
