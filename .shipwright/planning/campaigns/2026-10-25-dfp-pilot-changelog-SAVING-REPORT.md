# Saving report: deterministic-first pilot of `/shipwright-changelog` (programme P24)

Written by unit P7 on 2026-11-24, tree = `main` @ `05402f731` plus the P7 diff. "Before" = the P0 measurement (`...-P0-REPORT.md` section 3, tree `92dfee901`, 2026-11-14). Both sides: JUnit durations, one pytest process per root, the roots run in parallel on one busy Windows machine, so the big roots are slower than what an iterate or CI pays; compare the shape, not the second. The operator's aim (programme P24): fewer tests that run without anyone knowing what they protect, and shorter CI runs. **The conversion did not reach the second aim, and says so below.**

## Test counts and wall-clock, per root

| Root | Before (P0) | After (P7) | Change |
|---|---|---|---|
| `plugins/shipwright-changelog/tests` | 111 tests, 7.1 s | **661 tests, 1,646.7 s** (27 min 27 s); 212 of them in `tests/golden/` take 1,579 s, the other 449 take 67 s | +550 tests; time x230 |
| `shared/tests` | 14,681 tests, 1,483 s | 15,244 tests (15,242 passed, 2 failed in the first run, both fixed and re-run green, see FINDINGS D68), 2,441 s | +563 tests |
| `integration-tests` | 685 tests, 403 s | 684 passed (7 deselected), 544 s | -1 |
| `shared/scripts/tools/tests` | 1,502 tests, 186 s | 1,621 passed, 30 skipped, 224 s | +119 (41 new tests of the checker and the reader, the inventory checker's tests removed; the rest came with P1 to P6) |
| `shared/scripts/tests` | 704 tests, 25 s | 704 passed, 3 skipped, 32 s | 0 |

Where the changelog root's time goes: `test_driver_cli.py` 73 tests 665 s (every scenario through the CLI with real `git`), `test_p4_decisions.py` 17 tests 256 s, `test_promise_release.py` 17 tests 150 s, `test_scenarios_*` 95 s + 67 s + 66 s. These are the frozen golden harness (traces replayed in scratch repositories), not the retired pins.

## Pins, orphans, prompt lines

| Measure | Before | After |
|---|---|---|
| Tests that fail when the prose is replaced by a placeholder (pins) | 30 tests in 13 files | 14 tests as measured by P5 (FINDINGS P5 pin map: 17 at P5's start, 14 after). **Not re-measured in P7** (it needs the five roots run again with the prose broken, about 75 minutes of machine time); the cross-plugin guards are 4 of the 14 and constraints, not pins |
| Pins replaced | - | 4 flag-wiring pins and 7 event-block tests turned into code tests (P4, P5); 0 deleted without a replacement |
| Orphan tests removed | - | **0** (no per-test operator approval list exists; operator decision; candidates in FINDINGS D61: none by the programme's definition, two files by the dead-path reading) |
| Tests retired with their tool | - | the inventory checker's test file, `test_coverage_checks.py` (7 tests; its P8c twin pair and the orphan-trace guard live on in `test_scenario_index.py`, 3 tests) |
| `SKILL.md` | 440 lines | **263 lines** (-177, -40 %); bloat entry lowered to 263 (P6) |
| `references/*.md` | 707 lines (10 files) | 712 lines (the references now describe code; five were edited for F7 and the history sentences) |
| Prompt lines total | 1,147 | 975 (-172) |
| Code the prose moved to | - | `scripts/release.py` + `scripts/lib/release_*.py` + hooks: 1,693 lines, all with in-process tests |
| Shell blocks in `SKILL.md` | many chains | one command per fenced block, the one allowed multi-command block is the Step 4 pair; kept by the ratchet (P6) |

## What the numbers say

1. **The prompt got 40 % shorter and the mechanics now run in tested code**: that is the saving. Every behaviour of today's prose is pinned by 43 traces and 20 promise tests, which is what the extra tests are.
2. **Test count and CI time went up, not down**, exactly as the programme predicted ("L2 adds tests"). The changelog root costs about 27 minutes in this loaded measurement (the CI runner's figure for that root was not measured here). The cost is the golden harness: real git in scratch repositories, run once through the replay driver and once through the CLI driver. Two levers for the follow-up, none taken: mark the CLI-driver scenarios `slow` for the PR gate and run them nightly (the promise lock hashes `slow`, so a promise test cannot move silently), or share one scratch repository per scenario family.
3. **Pins fell from 30 to 14** (P5's measure), no pin was deleted without a replacement, and none is left that only reads a sentence.
4. **No test that ran without anyone knowing what it protects was removed**: the only removals are the retired inventory checker's tests and the P8a/P8b coverage tests, which tested scaffolding.

## Not measured

CI wall-clock per job (needs a run on `main`); the pin count after P5 on this tree; per-test coverage ("nothing lost" is not claimed, programme P18); token cost of the pilot (LEARNINGS item 1 says what was and was not recorded).
