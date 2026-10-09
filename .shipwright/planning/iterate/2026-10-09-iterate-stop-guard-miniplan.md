# Mini-Plan: iterate-stop-guard

- **Run ID:** iterate-2026-10-09-iterate-stop-guard

## Files
- new `shared/scripts/lib/iterate_stop_guard.py` — decision logic, transcript scan, next-phase hint, state
- new `plugins/shipwright-iterate/scripts/hooks/iterate_stop_guard.py` — thin Stop hook, fail-open
- new `shared/scripts/tools/record_hard_blocker.py` — CLI recording the legitimate early stop
- edit `plugins/shipwright-iterate/hooks/hooks.json` — register first in Stop
- new `references/autonomous-contract.md`; edit `SKILL.md` (rule + index row)
- edit `docs/hooks-and-pipeline.md`, `.shipwright/planning/01-adopted/spec.md` (AC43)
- new `plugins/shipwright-iterate/tests/test_iterate_stop_guard.py`

## Work breakdown
1. Lib + tests (decision, counters, blocker, detection, hint).
2. Hook + subprocess tests, hooks.json.
3. Docs: SKILL.md rule, reference, hooks-and-pipeline, spec AC.

## Test strategy
Unit tests on the lib; end-to-end hook subprocess tests (block, interactive, retired pointer, loop unit, blocker). Integration coverage (`cross_component`): the hook running as a subprocess against a real pointer is the composition test.

## Alternative approach
Detect "done" via `gh pr view` at Stop time instead of the run pointer; or put an `if:` filter on the hook. Both considered — see the review for the trade-off.
