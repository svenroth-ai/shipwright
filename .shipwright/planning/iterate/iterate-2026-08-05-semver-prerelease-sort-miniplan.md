# Mini-Plan: semver-prerelease-sort

- **Run ID:** iterate-2026-08-05-semver-prerelease-sort

## Files to create/modify

| File | Change type |
|---|---|
| `scripts/cache_tree_compare.py` | edit — fix `version_key` |
| `shared/templates/hooks/ensure_shared_cache.py` | edit — fix `_version_key` (canonical vendoring source) |
| `plugins/{adopt,build,changelog,compliance,deploy,design,iterate,plan,project,run,security,test}/scripts/hooks/ensure_shared_cache.py` (12 files) | edit — byte-identical re-vendor from the canonical template |
| `shared/tests/test_cache_tree_compare_version_key.py` | new — direct unit tests for the previously-untested canonical `version_key`/`latest_cache_version_dir` |
| `shared/tests/test_ensure_shared_cache_walk.py` | edit — extend `test_version_key_orders_numerically_not_lexically`'s neighborhood + add `_plugin_mirrors` behavioral case |
| `shared/tests/test_ensure_shared_cache_ssot_pins.py` | edit — extend equivalence-pin name list + add correctness assertion for both copies |
| `shared/tests/test_plugin_cache_version_resolution.py` | edit — add fallback-consumer regression case |

## Work breakdown

1. Write failing tests first, against the CURRENT (buggy) code, in all 4
   touched test files/new test file. Confirm they fail for the identified
   root cause (raw string-tail comparison), not an unrelated harness issue.
   — DONE, verified 6/6 new assertions fail with the expected AssertionError
   shape before any fix.
2. Fix `scripts/cache_tree_compare.py::version_key`: insert an
   "is-release" flag (`0` for any non-empty suffix, `1` for a bare
   release) as the 4th tuple element, ahead of the suffix string itself,
   so the release always sorts last among same-triplet names regardless
   of what the suffix text says. — DONE.
3. Apply the identical fix to `shared/templates/hooks/ensure_shared_cache.py`'s
   `_version_key` (stdlib-only, cannot import `cache_tree_compare`). — DONE.
4. Byte-copy the canonical template into all 12 plugin hook files
   (`cp shared/templates/hooks/ensure_shared_cache.py
   plugins/<name>/scripts/hooks/ensure_shared_cache.py`), confirming
   `test_ensure_shared_cache_vendored.py` (the drift gate) stays green. — DONE.
5. Re-run every touched test file: confirm all 6 new/extended assertions
   now pass, and no existing assertion in the same files regressed
   (52/52 green). — DONE.
6. Run the full `shared/tests` suite (`not slow and not cross_plugin`) to
   confirm no unrelated regression — IN PROGRESS (background).
7. Confidence Calibration + Test Completeness Ledger populated in the
   iterate spec. — DONE.
8. External LLM review (medium auto-trigger). — PENDING.
9. Full Code Review cascade (spec-reviewer → code-reviewer →
   doubt-reviewer, standing grant per root `CLAUDE.md`). — PENDING.
10. Finalization F0–F12. — PENDING.

## Test strategy

- No new production runtime path is added — this is a pure comparison-key
  bugfix — so the test strategy is unit-level, at every layer the bug is
  reachable from:
  - the function itself (`version_key`/`_version_key`), both
    implementations, both directly and via the SSoT equivalence pin;
  - the one real consumer of the *shared* implementation
    (`latest_cache_version_dir`, exercised through both a direct call and
    through `check_plugin_cache_sync.py`'s no-authority fallback — the
    second is the `category: integration` case, since it proves the
    fixed key composes with the real directory-resolution + sync-report
    pipeline, not just the key function in isolation);
  - the one real consumer of the *hook's* implementation
    (`_plugin_mirrors`, the self-heal repair-source picker — also
    `category: integration` for the same reason, and the more
    consequential of the two since the triage item names it as the
    completeness AUTHORITY the healer would otherwise trust).
- No E2E/browser layer applies (no UI, no web/API surface) — Verification
  surface is `cli`, satisfied by the pytest run itself (F0.5 executes the
  named runner command and requires `tests_run > 0`).
- `not-a-version` / empty-string / bare-numeric fallback cases were
  already covered pre-fix and are asserted unchanged (no regression) in
  `test_orders_numerically_not_lexically` / the existing
  `test_version_key_orders_numerically_not_lexically`.

## Alternative approach (considered, rejected)

**Alternative: parse a proper `packaging.version.Version` (or a hand-rolled
dot-separated prerelease-identifier comparator) instead of the flag-plus-
string-tail tuple.** This would give full SemVer precedence — e.g.
correctly ordering `1.0.0-alpha.1` before `1.0.0-alpha.2` before
`1.0.0-beta`, which the chosen fix does NOT attempt (prereleases of the
same numeric version still compare by raw suffix string, unchanged).

**Rejected because:**
- The hook's mirror is explicitly stdlib-only (`shared/templates/hooks/ensure_shared_cache.py`
  repairs the very `shared/` tree it would otherwise import a `packaging`
  dependency from) — a `packaging`-based fix could not be vendored into
  the hook at all, reopening exactly the "duplication with a pin" problem
  this codebase already solved for the simpler case (`test_ensure_shared_cache_ssot_pins.py`'s
  own docstring: "the duplication is justified (stdlib-only)").
- The triage item (trg-18da39b0) scopes the fix narrowly: "SemVer says the
  opposite [of the current bug]... a fix belongs in
  `cache_tree_compare.version_key`... plus a case covering `1.0.0-rc1` vs
  `1.0.0`" — it does not ask for full prerelease-identifier precedence,
  and the bug is explicitly "latent, not live" (every installed plugin
  today carries exactly one plain `MAJOR.MINOR.PATCH` version), so there
  is no live case to justify the larger surface area.
- A hand-rolled full-precedence comparator is meaningfully more code (and
  more edge cases: numeric vs alphanumeric identifier comparison, build
  metadata exclusion) duplicated across 13 vendored copies, for a
  precedence class (`-alpha.1` vs `-alpha.2`) that has never once been
  measured in this cache's real directory listing.
