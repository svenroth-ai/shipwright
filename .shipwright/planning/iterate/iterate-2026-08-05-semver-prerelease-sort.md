# Iterate Spec: semver-prerelease-sort

- **Run ID:** iterate-2026-08-05-semver-prerelease-sort
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal
`scripts/cache_tree_compare.version_key` and its stdlib-only mirror
(`_version_key` in `shared/templates/hooks/ensure_shared_cache.py`, vendored
byte-identically into 12 `plugins/*/scripts/hooks/ensure_shared_cache.py`
copies) compare a SemVer suffix as a raw string tail, so `1.0.0-rc1` sorts
AFTER `1.0.0` (`'-rc1' > ''` lexically) and would be picked as the newest
installed version. Fix both implementations so a release outranks every
prerelease of the same numeric version, per SemVer.

## Acceptance Criteria
- [x] `cache_tree_compare.version_key("1.0.0") > version_key("1.0.0-rc1")`,
  and `latest_cache_version_dir` picks a release directory over a
  co-located prerelease of the same numeric version.
- [x] The vendored hook mirror `_version_key` in
  `shared/templates/hooks/ensure_shared_cache.py` implements the identical
  fix, and `_plugin_mirrors` picks the release directory as the repair
  source over a co-located prerelease of the same numeric version.
- [x] The canonical template is re-vendored byte-identically into all 12
  `plugins/*/scripts/hooks/ensure_shared_cache.py` copies
  (`test_ensure_shared_cache_vendored.py` stays green).
- [x] `test_ensure_shared_cache_ssot_pins.py`'s equivalence pin gains a
  `1.0.0-rc1` case, and both implementations are additionally asserted
  correct (release > prerelease), not merely equal to each other.

## Spec Impact
- **Classification:** none
- **NONE justification:** internal bugfix to a monorepo-only tooling helper
  (plugin-cache version comparison) — restores the SemVer-intended
  ordering the code already claims to implement (per its own docstring
  citing Gemini-S1/OpenAI-M2); no product-facing FR describes cache
  version-directory selection.

## Out of Scope
- Full RFC-8288-style SemVer precedence across multiple dot-separated
  prerelease identifiers (e.g. `-alpha.1` vs `-alpha.2` vs `-beta`) — only
  the release-outranks-prerelease defect named by the external review is
  in scope. Ordering among different prereleases of the same numeric
  version keeps its existing (string) comparison, unchanged by this fix.
- `check_plugin_cache_sync.py`'s own resolver, which already prefers
  `installed_plugins.json` over `latest_cache_version_dir` when available
  (P1.08 / #527) — this fix only affects the fallback path and the
  self-heal hook, which have no such authority to consult.
- Joining the cross-plugin mirror tree to the drift check
  (trg-5005bf57) — unrelated follow-up already tracked separately.

## Design Notes
n/a — no UI surface; pure Python comparison-key logic + tests.

## Affected Boundaries
n/a — `version_key` takes an in-memory directory-name string and returns an
in-memory tuple; no serialized format crosses a process/file boundary here.
`touches_io_boundary` did not fire (confirmed via the diff-driven detector
in Repo Scout).

## Confidence Calibration
- **Boundaries touched:** n/a (see Affected Boundaries)
- **Empirical probes run:**
  - Reproduced the bug pre-fix: `sorted(["1.0.0-rc1", "1.0.0"], key=version_key)`
    returned `['1.0.0', '1.0.0-rc1']` (prerelease sorts as "newest").
  - Reproduced the same failure at the real consumer layer: `check_sync`'s
    fallback picked the empty `1.0.0-rc1` cache dir over the `1.0.0` dir
    holding files, reporting spurious `drift`.
  - Post-fix: all 6 new/extended tests plus the existing 46 tests in the
    5 touched files pass (52/52); the byte-identity vendoring gate
    (`test_ensure_shared_cache_vendored.py`) stays green across all 12
    plugin copies + the canonical template.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `cache_tree_compare.version_key` ranks a release above a prerelease of the same numeric version | tested | `test_cache_tree_compare_version_key.py::test_a_release_outranks_every_prerelease_of_the_same_version` PASSED |
  | 2 | `version_key` still orders purely numeric triplets correctly (no regression) | tested | `test_cache_tree_compare_version_key.py::test_orders_numerically_not_lexically` PASSED |
  | 3 | The release-vs-prerelease flag does not override the numeric triplet (a newer prerelease still beats an older release) | tested | `test_cache_tree_compare_version_key.py::test_prerelease_ordering_does_not_leak_across_numeric_versions` PASSED |
  | 4 | `latest_cache_version_dir` (the one real consumer) picks the release directory, not a co-located prerelease | tested | `test_cache_tree_compare_version_key.py::test_latest_cache_version_dir_picks_the_release_over_a_prerelease` PASSED |
  | 5 | The vendored hook's `_version_key` implements the identical fix | tested | `test_ensure_shared_cache_walk.py::test_version_key_ranks_a_release_above_its_own_prereleases` PASSED |
  | 6 | The hook's `_plugin_mirrors` (the self-heal repair-source picker, the AUTHORITY-on-completeness consumer named in trg-18da39b0) picks the release dir over a co-located prerelease | tested — **category: integration** | `test_ensure_shared_cache_walk.py::test_plugin_mirrors_picks_a_release_over_a_prerelease_of_the_same_version` PASSED — proves the fixed key composes with the real directory-walk/pick pipeline, not just the key function in isolation |
  | 7 | The two implementations (`cache_tree_compare.version_key` and the hook's `_version_key`) stay equal on a `1.0.0-rc1` input, and both independently implement the correct release-outranks-prerelease semantics | tested | `test_ensure_shared_cache_ssot_pins.py::test_version_key_is_equivalent_to_the_shared_implementation` + `::test_version_key_ranks_a_release_above_its_own_prereleases_in_both_copies` PASSED |
  | 8 | `check_plugin_cache_sync.py`'s no-authority fallback path (the OTHER named consumer: "latest_cache_version_dir would report the prerelease as the cache's current version") does not report a prerelease-holding dir as in sync when the release dir alongside it holds the real files | tested — **category: integration** | `test_plugin_cache_version_resolution.py::TestFallbackIsHonest::test_the_fallback_does_not_pick_a_prerelease_over_its_own_release` PASSED |
  | 9 | The 12 re-vendored plugin copies stay byte-identical to the fixed canonical template | tested | `test_ensure_shared_cache_vendored.py` (all 13 forward/reverse identity tests) PASSED |

- **Confidence-pattern check:** Asymptote (depth) — no prior "are you
  confident?" question produced a "yes" that a subsequent probe then
  contradicted in this run; this is the first and only probe cycle.
  Coverage (breadth) — every ledger row is `tested`, 0 untested-testable.
  `cross_component` risk flag fired (both `ensure_shared_cache.py` sites
  match `**/hooks/*.py`); rows 6 and 8 above are the two
  `category: integration` behaviors satisfying `check_integration_coverage`
  — one per named real-world consumer (the self-heal hook's repair-source
  pick, and the sync checker's fallback pick), not just the shared
  `version_key` function tested in isolation.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_cache_tree_compare_version_key.py shared/tests/test_ensure_shared_cache_walk.py shared/tests/test_ensure_shared_cache_ssot_pins.py shared/tests/test_plugin_cache_version_resolution.py shared/tests/test_ensure_shared_cache_vendored.py -v` (run from `shared/`)
- **Evidence path:** `.shipwright/runs/iterate-2026-08-05-semver-prerelease-sort/surface_verification.json`
