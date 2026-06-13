# Mini-Plan: code-simplify-skill (OS1 / P3.2)

- **Run ID:** iterate-2026-06-13-code-simplify-skill
- **Approach:** Variant A+ — sub-skill `F-simplify.md` + non-dodgeable `behavior_snapshot.py`.

## Build order (TDD)

1. **`behavior_snapshot.py` (tests first).** Pure gate logic + I/O boundary.
   - Pure: `build_snapshot(run_result) -> dict`, `compute_verdict(snapshot, current) -> Verdict`.
   - Impure (CLI-wired): `run_test_suite()`, `collect_test_ids()`, `measure_loc()`.
   - I/O: `write_snapshot()` / `read_snapshot()` → `.shipwright/runs/<run_id>/behavior_snapshot.json`.
   - CLI: `snapshot` / `verify` subcommands; `verify` exits non-zero on any reject condition.
   - Tests (`tests/test_behavior_snapshot.py`): verdict matrix (green→green PASS; status-flip
     REJECT; removed-test-id REJECT; loc-drop+test-drop REJECT; loc-drop-only PASS), round-trip
     (AC6), CLI probe against a synthetic suite (AC7 — both arms).

2. **`classify_intent.py`.** Add `SIMPLIFY_KEYWORDS` + multi-word `clean up`/`cleanup`/`clean-up`.
   `mode = "simplify"` additive field; `type = "change"` when simplify wins and no bug keyword.
   Extend `tests/test_classify_intent.py` (simplify→change+mode; refactor stays change+no mode;
   `fix and simplify`→bug+no mode; confidence).

3. **`F-simplify.md` (NEW).** Mirror `F-debug.md` shape: Five Principles, Chesterton-Fence
   pre-flight, Behavior-Snapshot→Simplify→Behavior-Verify wrap (cites `behavior_snapshot.py`),
   reviewer gate, MIT attribution footer. `tests/test_f_simplify_routing.py` mirrors
   `test_f_debug_routing.py`.

4. **`SKILL.md`.** `## Path D: SIMPLIFY` section + Phase Index row + "D. Determine Intent Type"
   note + Phase Matrix row for the snapshot wrap. Re-check `test_skill_phase_matrix.py`,
   `test_skill_completeness_matrix.py`, `test_skill_references_link.py` stay green.

5. **`docs/guide.md`.** Intent-Paths section + the snapshot-wrap paragraph; confirm no test
   pins the literal "three intent" count before editing.

## Alternatives considered (decision trace)

- **New top-level `simplify` intent type** (rejected): ripples into `iterate_entry._VALID_TYPES`,
  the `IterateEntry` TypedDict, and changelog category mapping. Chosen instead: `simplify` is a
  **sub-mode of CHANGE** (`type:"change"` + additive `mode:"simplify"`) — zero F5c blast radius,
  semantically correct (you *are* changing code, behavior preserved).
- **Per-test pytest-output parsing for the gate** (rejected): brittle, version-sensitive.
  Chosen: compare collected **node-id sets** + counts + exit_code → robust, dependency-free,
  and directly expresses "removed coverage".
- **Variant B mini-plugin** (rejected by user): full registration tax, duplicates the pipeline.
- **Prose-only A** (rejected by user): acceptance ("store hash / reject on flip") is mechanical,
  so it deserves a real verifier, not an honor-system.

## Risk / safety

- Diff-driven `touches_io_boundary` (json.dump/load) → Boundary Probe + round-trip (AC6). Planned.
- No `cross_component` (no merge/churn/hook/phase-validator files). No integration-coverage gate.
- Keep all existing drift-protection tests green; add two new test files.
