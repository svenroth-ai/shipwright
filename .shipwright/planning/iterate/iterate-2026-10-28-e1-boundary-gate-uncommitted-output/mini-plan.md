# Mini-plan E1: design boundary gate vs earlier phases' uncommitted output (F1, FR-01.04 #11)

Problem: `check-design-gates.py --gate boundary` judges the WHOLE dirty working tree via `git_dirty_paths`. The project phase leaves its outputs uncommitted, so the gate flags them and the design agent stops to ask "commit earlier output first?" in every brief run.

Change:
1. New `plugins/shipwright-design/scripts/lib/boundary_baseline.py`: snapshot of dirty paths with sha256 content fingerprints; `write_baseline`, `load_baseline`, `session_changes` (dirty minus unchanged-since-baseline).
2. `setup-design-session.py` writes `.shipwright/designs/.boundary-baseline.json` at session start (inside the allowed prefix).
3. `boundary_gate` filters `git_dirty_paths` through `session_changes`. No baseline = strict (old behaviour). Path edited after baseline = still flagged. New path = flagged.
4. Docs: `review-loop.md` gate table, `SKILL.md` one sentence.
5. Tests: 4 new in test_check_design_gates.py (tagged FR-01.04/AC12), cache-layout test copies the extra shared module.
Risks: resume re-runs setup and re-baselines (design edits before resume would be hidden) - accepted, same documented assumption as phase_write_boundary.
