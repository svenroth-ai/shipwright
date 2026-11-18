# Mini-plan: promise-hash hardening (iterate-2026-11-18-promise-hash-hardening)

Complexity: medium. Intent: change. AC record: `unchanged` for FR-01.09 (test code, testkit and docs only).

## Work
1. Tests first (`shared/tests/test_promise_hash_hardening.py`), one per blind spot, all red before the fix:
   import binding hashed (alias swap), every binding of a name in file order (def then rebinding), autouse unless literal
   False, `pytest_*` hooks in every closure, `pytestmark` from Assign/AnnAssign/AugAssign via one helper, a pinned digest of
   an f-string-heavy source, `path::name` lock keys with a missing name a failure.
2. `shared/testkit/promise_hash.py`: one ordered binding list per name (defs, consts, imports); `always()` names; shared
   target helper; refuse a rebound test name. Split `promise_lock.py` (AC ids, `lock_entry`, `lock_key`, `lock_problems`)
   to stay under 300 lines.
3. Meta test: no import under another name (`asname not in (None, name)`), every promise test reaches `oracle` through its
   own closure, fingerprints keyed `path::name`. Promise tests write `scenario_support.x` in full.
4. `test_trace_freeze.py` REQUIRED: the lock modules, their tests, the parent conftests, the root conftest, the package
   `__init__.py` files (chosen over hashing them into every closure: simpler).
5. Promise tests: AC04 footer + chore-only cases and the dead condition removed; AC10 sentence narrowed (the whole-release
   preview is not observable); AC11 aggregation half through a new oracle function, note says trivially held; AC13 checks
   package.json and the catalog; the refused AC12 run asserts the exact committed map and the release commit.
6. FINDINGS (remove fixed blind spots, keep the rest), LEARNINGS (append), docs/hooks-and-pipeline.md (helper paragraph).

## Verification
Shared hash tests, golden root (Windows works), ruff, `scripts/verify_local.py`, one `--junitxml` per root.
