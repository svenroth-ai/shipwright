# Mini-plan: P2p - promise tests, promise list, judgement scenarios, the lock's hashing (changelog pilot)

Complexity: medium. Test-support only: no skill, script or product code changes (the unchanged skill is the oracle).

## Goal
On top of the replay driver, oracle and scenarios S1-S19 (merged), add what the operator's stop 2 locks besides the
traces: tests for the promises of FR-01.09 (AC01-AC15), a promise list in the AC shape of the skill-check trace record,
the three judgement questions as `scenarios.json` (compare_runs.py schema), and the stdlib hashing helper the promise lock uses.

## Approach
1. `shared/testkit/promise_hash.py`: normalized AST of a test plus every same-module helper, constant and fixture it uses
   (conftest fixtures handed in); ignores formatting, comments, docstrings, import order, `pytest.mark.*` except
   `parametrize`; own serializer (no `ast.dump`, which differs across Python versions); AC ids from `covers`, resolved
   through `## AC-Move-Map`, stored beside the hash. Tests in `shared/tests/test_promise_hash.py`.
2. `test_promise_aggregate.py` (AC02, AC03, AC05-AC10, AC11 aggregation half) and `test_promise_release.py` (AC01, AC04,
   AC12-AC15): each calls `ReplayDriver` / `release_flow` only and judges through `oracle`. 20 tests.
3. `promise_list.json`: id, sentence, source anchor (file, heading path, content hash of the AC text), class, check,
   status (six values), decision, oracle (`test`/`trace`/`scenario`). AC11 as a whole is a `gap` (D2), its aggregation half passes.
4. `scenarios.json`: eight scenarios for version suggestion, Step 5 preview and out-of-sequence warning.
5. `test_promises_meta.py`: shape and statuses of the list, interface rule, covers tags, scenarios schema, fingerprint.
6. New test files join `REQUIRED` of `test_trace_freeze.py`. No lock file (stop 2).

## Tests
Green on the unchanged skill; the meta tests go red for a dangling check, an uncovered AC, a forbidden import, a scenario
with a bad decision; the hash tests prove what the fingerprint ignores and what it must notice.

## Alternative approach considered
Reuse the scenarios as the promise tests (tag the existing S-tests): rejected - a scenario test compares a whole trace,
so any trace change would read as a change of a promise; a promise test states one promise and nothing else.

## Confidence Calibration

Boundary: product code to promise tests (do the promise tests go red when the promise is broken). Seeded mutations, each reverted at once (the tree holds no product change):

1. `aggregate_changelog._render_versioned_section`: category bullets never counted as content. 10 of 12 aggregate promise tests went red. Caught.
2. `git_utils.suggest_version_bump`: a breaking change bumps the minor, not the major. The AC04 `2.0.0` case went red. Caught.
3. Same renderer, release date dropped from the version heading. All 12 stayed green. No FR-01.09 AC promises the date in the heading, so this is a gap in the promise list, not a bug in a test. Not probed further; recorded as an edge case that is acceptable here (the golden trace scenarios carry the heading text).

Two consecutive probes found nothing wrong with a test (1, 2); probe 3 shows where the promises stop.
