# Mini-plan: P3 release CLI prepare + aggregate

Goal: `release.py prepare|aggregate` (JSON out, thin wrappers, injected runner); SKILL.md Steps A-4 become one call each;
gates from the catalog (A2/C1/F12), upgrade-notes check in code (A3), release date + run id stored once (A6/F14), aggregate owns
the dry-run/real flag rules (A4).

Files: scripts/release.py; scripts/lib/release_{runner,paths,runstate,gates,upgrade_notes,prepare,aggregate}.py; tests/golden/
driver_cli.py + test_driver_cli.py (scenarios + promise tests through the CLI); tests test_release_*.py (L1 + boundary + the
orchestrator path in four layouts); SKILL.md / first-actions.md / release-workflow.md; docs/hooks-and-pipeline.md rows;
inventory data; coverage.py table follows the inventory; approved_deltas.json (4 entries); promise_list.json anchor hashes.

Order: tests first for each moved behaviour (gates from catalog, upgrade drop, run state across processes), then code, then prose,
then deltas, then `golden_lock.py --check`.
Risk: frozen prose/coverage.py deltas; traces must not move (driver_cli maps JSON back to the whitelisted trace fields).
Verification: full changelog root, `verify_local.py`, ruff.
