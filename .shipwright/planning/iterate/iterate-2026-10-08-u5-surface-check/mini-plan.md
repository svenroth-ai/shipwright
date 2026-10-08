# Mini-plan: U5 - Surface check not bypassable (iterate-2026-10-08-u5-surface-check)

Problem: at medium+ F0.5 accepts `surface: none` with any free-text justification, and F11
(`check_surface_verification`) trusts the block's self-reported `tests_run` / `exit_code`. Both are typed by the run
itself. A UI or API change can claim `none`, and a real surface can claim numbers no runner produced.

1. Closed vocabulary: new `surface_none` family in `shared/scripts/lib/reason_codes.py` (`docs-only`, `test-only`,
   `build-config-only`, `no-behavior-change`, `no-startable-surface`).
2. Producer: `surface_verification.py --reason-code` (validated against the family; invalid -> exit 4, block carries
   `error`; valid -> recorded in the block). Net lines <= 0 (grandfathered at 463; argparse compacted).
3. `verifiers/_surface_detect.py`: path-based detection of the four runnable-surface kinds (ui via
   `detect_frontend_changes`, api_route, realtime, message_contract); tests, fixtures, prose, `docs/`, `.github/` and
   finalization records never count. Singular `route`/`router` names excluded (dispatch logic in a tooling repo;
   calibrated on all tracked files of this repo).
4. `verifiers/_surface_evidence.py`: cross-check against the staged evidence (`evidence_drop` provenance + in-memory
   index via `fresh_evidence`): absent / other run_id / head_commit not an ancestor of the verified commit (stale) /
   web without a Playwright report / any failing staged result / fewer passes than `tests_run` / a runner-named test
   path without a passing result -> fail. Collector unavailable -> fail (never a skip).
5. `verifiers/surface_check.py`: `check_surface_verification(project_root, run_id, commit_hash="")` moved out of
   `iterate_checks.py` (shrinks it, re-exported, `run_all_checks` now passes the commit). `none` at medium+ needs
   justification + closed code, and the branch diff (merge-base..commit via `_cascade_trigger_inputs.measure_diff`)
   must touch no runnable surface; an unmeasurable diff or a non-git tree cannot confirm `none`.
6. Docs: F0.5.md (Step 1 + conditions 5/6), SKILL.md F0.5 paragraph (same line count), F5c.md, guide.md,
   hooks-and-pipeline.md paragraph.
7. Tests (tagged FR-01.11/AC07): `test_surface_check.py` (real git + production staging; absent and stale both
   tested), `test_surface_detect.py` (rules + producer); superseded positive-path tests in
   `test_verify_iterate_finalization.py` removed (file at its cap), attribution/CLI tests retargeted.

Out of scope: refusing `cli` when UI is detected (Backend-affects-Frontend stays prose), producer-side diff detection.
