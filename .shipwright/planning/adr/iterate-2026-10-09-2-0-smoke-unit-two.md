# Smoke unit 2: marker-file presence check (PR #860 campaign smoke)

Run: `iterate-2026-10-09-2-0-smoke-unit-two` · campaign `smoke-860-20261009`, sub-iterate 2.0 ·
throwaway, never merged.

## Change

- `scripts/_smoke_check.py` — stdlib CLI: exit 0 when `docs/_smoke/unit-2.md` is a regular, UTF-8
  readable file with visible text (after dropping Unicode `Cf` format characters), else exit 1.
  Default root comes from the script location, not the cwd.
- `docs/_smoke/unit-2.md` — one-line marker.
- `shared/tests/test_smoke_unit2.py` — 18 tests (subject loaded by path, ADR-045).

**Spec deviation:** the spec names `tests/test_smoke_unit2.py`. There is no repo-root `tests/`,
and the root `conftest.py` enforces one registered test root per pytest process, so the test
lives in the existing `shared/tests` root (permitted by the orchestrator brief).

**De-facto acceptance criteria** (the campaign-owned spec says `TBD`; the runner does not edit
it): missing → exit 1; directory at path → exit 1; unreadable / non-UTF-8 → exit 1;
whitespace- or format-character-only → exit 1; visible text → exit 0; committed doc → exit 0
from any cwd. Every one is a test.

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes · **Verdict:** approve · **Severity:** low
- **Findings:** necessity/low — throwaway vehicle, nothing smaller still tests the runner (accepted);
  completeness/low — ACs TBD (disclosed: listed above); completeness/low — root `tests/` not a
  registered root (fixed: `shared/tests`); complexity-cost/low — merge safety (disclosed:
  `SHIPWRIGHT_ITERATE_AUTOMERGE=0`, orchestrator opens the PR, never merged).
- **Status:** 1 fixed, 3 disclosed

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes · **Severity:** low
- **Findings:** completeness/medium — ACs TBD (disclosed, listed above); completeness/low — test
  location deviation (fixed: recorded here); architecture/low — subprocess-only `main()` coverage
  (fixed: in-process `main()` test); architecture/low — cwd-dependent root (fixed: explicit root +
  script-relative default); architecture/low — unreadable file traceback (fixed); architecture/low —
  smoke debris in `docs/` (disclosed: branch never merged).
- **Status:** 4 fixed, 2 disclosed

## Architecture Review (external, --mode architecture)
- **Verdicts:** glm approve · openai approve. GLM suggested dropping the test (rejected-with-reason:
  the spec requires a test and the smoke needs one collected).

## External-Plan-Review-Findings (glm revise · openai revise)

| Finding | Severity | Disposition |
|---|---|---|
| ACs TBD; record test location (openai) | medium | accepted-and-fixed (ADR lists ACs + deviation; spec is campaign-owned) |
| Root resolved from cwd (openai) | medium | accepted-and-fixed (script-relative default + cwd test) |
| Unreadable/decoding errors (openai) | low | accepted-and-fixed |
| Path-based loading is unneeded machinery (glm) | medium | rejected-with-reason: ADR-045 requires it for repo-root scripts |
| Test count disproportionate (glm) | low | rejected-with-reason: each test pins one exit branch |
| Accidental-merge risk (glm) | medium | rejected-with-reason: auto-merge disabled, branch discarded |
| Exact doc content unspecified (glm) | low | accepted: the doc's line is fixed and committed |

## External-Code-Review-Findings (openai approve · glm revise)

| Finding | Severity | Disposition |
|---|---|---|
| Test path deviates from spec (glm) | medium | rejected-with-reason: recorded deviation, one-test-root rule verified in `conftest.py` |
| `main()` prints during tests (glm) | low | rejected-with-reason: pytest captures stdout |

## Internal cascade
- **spec-reviewer:** PASS. **code-reviewer:** PASS (2 low: test boilerplate — declined, throwaway;
  loader assertion — fixed). **doubt-reviewer:** 1 medium + 2 low, all on invisible-character
  literals — all fixed by switching to a generic `unicodedata` `Cf` filter (no literals) and
  parametrized code-point tests with a `strip()` precondition.
- Code changed after Stage 1/2 read it (Cf filter, loader assertion); the orchestrator's 3f-bis
  re-runs the cascade on the final diff.

## Self-Review
1. Spec Compliance — pass: all three items delivered; location deviation recorded.
2. Error Handling — pass: every failure branch returns `(False, msg)` / exit 1.
3. Security Basics — pass: read-only, stdlib, no shell/network.
4. Test Quality — pass: 18 tests, each branch plus two real subprocess round-trips.
5. Performance Basics — pass: single small read.
6. Naming & Structure — pass: `_`-prefixed throwaway names, no dead code.
7. Affected Boundaries — pass: committed markdown → script reader, round-trip probe run.

## Confidence Calibration
- **Boundary:** committed markdown file → `_smoke_check.py` reader (human-edited format).
- **Probe 1** (BOM, BOM-only, BOM+ws, CRLF, CRLF-only, non-ASCII, NBSP, zero-width, UTF-16,
  HTML comment): **finding** — a zero-width-space-only file passed as non-empty. Fixed.
- **Probe 2** (same set after fix) and **Probe 3** (tab, ideographic space, ZWJ+text, WJ+BOM,
  line separator, NUL, emoji, 2 MB): no new findings. Doubt review then widened the fix to every
  `Cf` character; probes 2+3 re-run on the final code: no findings. Asymptote reached.
- **Not probed further, accepted:** a NUL byte or an HTML comment counts as content — the contract
  is "non-empty", not "meaningful".

## F2 / F3a
No structural impact (no route, schema, service, gate or convention) — F2 makes no edit. No
reusable learning beyond this run — F3a appends nothing.
