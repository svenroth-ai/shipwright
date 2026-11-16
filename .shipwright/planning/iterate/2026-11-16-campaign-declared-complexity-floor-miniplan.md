# Mini-Plan: campaign-declared-complexity-floor
Run ID: iterate-2026-11-16-campaign-declared-complexity-floor

## Files
- new `lib/declared_complexity.py` (parse the `Complexity:` line, apply_floor, validate); new `lib/campaign_unit_spec.py` (spec renderer, split out of `campaign_init.py`, which sits at its bloat cap); new `lib/risk_flag_args.py` (moved `_split_flags` so `diff_risk_recheck.py` stays under its grandfathered 305 lines).
- edit `classify_complexity.py` (declared floor, `declared_complexity` signal, `--declared-complexity`), `diff_risk_recheck.py` (`--spec`, `declared_complexity` in the block, floor in `effective`), `campaign_init.py` (`complexity` key), `risk_recheck_recording.py` (F11), the runner contract schema, `sub-iterate-runner.md` (one existing line gains `--spec`), the step-3-4 reference (one paragraph), spec.md AC52.
- tests: plugin unit, shared verifier, integration.

## Work breakdown
1. declared_complexity module + tests. 2. Stage 1 floor. 3. recheck floor + record. 4. planner emits the line. 5. F11 gate. 6. runner command + docs. 7. integration test.

## Alternative approach considered
Pass `--complexity` as an explicit CLI override from the runner (reading the brief). Rejected: the runner would have to find and parse the brief (not part of the unit spec it is given), and nothing would persist the decision; the spec line travels with the unit and both classification points can read it.
