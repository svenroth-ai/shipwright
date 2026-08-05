# Iterate Spec: bloat-baseline-vendored-hook

- **Run ID:** iterate-2026-08-05-bloat-baseline-vendored-hook
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal
The prior iterate (iterate-2026-08-05-semver-prerelease-sort, merged as PR
#556) left `scripts/cache_tree_compare.py` at 305 lines (crossing the
300-line guideline) and `shared/templates/hooks/ensure_shared_cache.py`
(+ its 12 byte-identical vendored plugin copies) at 325 lines, growing an
ALREADY-over-limit file (317 lines pre-existing, undetected because no
prior session's Stop hook had fired on it). The session's own bloat-gate
Stop hook blocked completion on both. Trim the added prose to the
essential minimum and formally register the vendored hook's pre-existing
overage as accepted debt, so the gate clears honestly rather than being
routed around.

## Acceptance Criteria
- [x] `scripts/cache_tree_compare.py` is back at or under the 300-line
  guideline (289 lines before the prior iterate touched it; 295 now —
  294 after the initial trim, +1 after the code-reviewer's request to
  restore a dropped citation, see Confidence Calibration).
- [x] `shared/templates/hooks/ensure_shared_cache.py`'s net growth from
  the prior iterate is minimized (was 317 pre-existing, 325 after that
  iterate's edit, 322 now — 321 after the initial trim, +1 after
  restoring a dropped scope-caveat pointer) and the file's pre-existing
  300+ overage is registered in `shipwright_bloat_baseline.json` as
  `state: grandfathered` (not `exception`, since no ADR-NNN number
  exists yet for either iterate — both are still pending
  `/shipwright-changelog` release).
- [x] All 12 `plugins/*/scripts/hooks/ensure_shared_cache.py` copies stay
  byte-identical to the canonical template (`test_ensure_shared_cache_vendored.py`
  green) and are each registered in the baseline at the same `current: 322`.
- [x] No logic/behavior change: the same 138 tests (52 from the prior
  iterate's touched files + 61 bloat-baseline/defense tests + 25
  test_bloat_defense_artifacts) that passed before this trim still pass
  unchanged after it.

## Spec Impact
- **Classification:** none
- **NONE justification:** repo-hygiene correction (comment/docstring
  density + a bloat-baseline data-file registration) to a monorepo-only
  tooling helper; no logic changed, no product-facing FR describes file
  size accounting.

## Out of Scope
- Splitting `shared/templates/hooks/ensure_shared_cache.py` into multiple
  files. It is a deliberately stdlib-only, single-file, byte-identically
  vendored SessionStart hook (it repairs the very `shared/` tree it would
  otherwise import from) — splitting it means either importing from
  `shared/` (breaks the self-repair design) or multiplying the vendoring
  surface across all 13 copies for no functional benefit. Registering the
  pre-existing overage as grandfathered debt is the proportionate fix.
- Any further SemVer/version_key logic change — that shipped in PR #556;
  this iterate is pure hygiene, zero behavior delta.
- Promoting the baseline entries to `state: exception` with a real
  ADR-NNN — no ADR number exists for either this run or the prior one
  until `/shipwright-changelog` release; `grandfathered` (adr: null)
  matches the 131 other undocumented pre-existing entries already in
  this baseline.

**Transparency note (external review, OpenAI M1):** the registered
`current: 322` covers BOTH the file's pre-existing 317-line overage AND
the 5 lines this run's own trim still leaves (down from the prior
iterate's +8; +4 after the initial trim, +5 after restoring the
code-reviewer's requested citation). This is not laundering the growth
silently — every other
`grandfathered` entry in this baseline already represents "size at time
of registration," not "size when first created" (the baseline has no
per-entry history), and the +4 is fully visible in this run's own commit
diff and PR description. The alternative — getting the file back to
exactly 317 — was rejected: it would mean dropping the one-line pointer
this fix needs to stay comprehensible (see Alternative approach below),
for a 4-line difference that changes nothing about whether the file is
grandfathered or not.

## Design Notes
n/a — no UI surface; comment/docstring trim + a JSON data-file registration.

## Affected Boundaries
n/a — no serialized producer/consumer boundary changes; the baseline JSON
edit adds data rows to an existing, already-covered schema (no new format).

## Confidence Calibration
- **Boundaries touched:** n/a (see Affected Boundaries)
- **Empirical probes run:**
  - Measured exact line counts before/after trim for both files
    (`wc -l`): cache_tree_compare.py 305→294→295 (was 289 pre-prior-iterate;
    +1 restoring the code-reviewer's requested citation);
    ensure_shared_cache.py template 325→321→322 (was 317 pre-prior-iterate;
    +1 restoring the code-reviewer's requested scope-caveat pointer),
    confirmed identical across all 12 vendored copies.
  - Confirmed the diff isolates cleanly against fresh `origin/main`
    (`git diff origin/main HEAD --stat`) — only the 14 hook-related files
    + the baseline JSON + log appends, nothing else.
  - Ran the full 138-test set (the 5 files the prior iterate touched +
    `test_bloat_baseline.py` + `test_bloat_defense_artifacts.py`) before
    AND after the trim — identical pass count, confirming the
    comment/docstring-only change altered no behavior.
  - **Direct probe against the real Stop-hook entry point** (external
    review, OpenAI M1+M2, both rounds): constructed the exact marker
    shape `check_file_size.py` writes (raw byte-newline count, the gate's
    own counter — not a bare `wc -l` assumption) for all 13 still-oversize
    hook files, then ran `bloat_gate_on_stop.py`'s own crossing-check rule
    against the real, current `shipwright_bloat_baseline.json` — not just
    the unit tests around its loader. Result: gate count matches the
    registered `current: 322` exactly for all 13 paths, all 13 resolve
    `in_baseline: True`, verdict `WOULD PASS` (re-run after restoring the
    code-reviewer's requested citations, same result). `cache_tree_compare.py`
    correctly excluded — at 295 lines it is back under 300, so the real
    `check_file_size.py` would never mark it in the first place.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | version_key/latest_cache_version_dir behavior is unchanged by the trim | tested | test_cache_tree_compare_version_key.py (4 cases) PASSED, identical to pre-trim |
  | 2 | The hook's _version_key/_plugin_mirrors behavior is unchanged by the trim | tested | test_ensure_shared_cache_walk.py (18 cases) PASSED, identical to pre-trim |
  | 3 | The two implementations still stay equivalent post-trim | tested | test_ensure_shared_cache_ssot_pins.py (7 cases) PASSED |
  | 4 | check_plugin_cache_sync.py's fallback-consumer behavior is unchanged | tested | test_plugin_cache_version_resolution.py (10 cases) PASSED |
  | 5 | The 13 vendored copies stay byte-identical post-trim | tested | test_ensure_shared_cache_vendored.py (13 assertions) PASSED |
  | 6 | The 13 new baseline entries are well-formed and loadable, and the Stop-hook's crossing check now finds each path in-baseline | tested — **category: integration** | test_bloat_baseline.py (61 cases) PASSED against the real `shared/scripts/lib/bloat_baseline.py` loader `bloat_gate_on_stop.py` reads from |
  | 7 | The bloat-defense artifact suite (fanout, drift-detection wiring) still passes with the new entries present | tested | test_bloat_defense_artifacts.py (25 cases) PASSED |

- **Confidence-pattern check:** Asymptote (depth) — this is the direct,
  first-pass fix for a concrete Stop-hook block; no prior "confident" claim
  was contradicted. Coverage (breadth) — every ledger row `tested`, 0
  untested-testable. `cross_component` risk flag fired (file-path match on
  `**/hooks/*.py`); row 6 is the `category: integration` behavior — it
  proves the new baseline rows compose with the REAL loader the Stop hook
  and `check_plugin_cache_sync.py` both read, not just JSON-shape in
  isolation.

## Verification (medium+)
- **Surface:** cli
- **Runner command (F0.5's `surface_verification.py` runs the command with NO
  shell and `cwd=project_root` — repo root, never `shared/` — so paths must be
  project-root-relative `shared/tests/...`, not bare `tests/...`. An earlier
  spec revision had this backwards in both directions before landing here:
  first a `shared/tests/...` path documented as "run from `shared/`" — wrong,
  would resolve to `shared/shared/tests/` (external review, OpenAI M2, round
  1) — then a bare `tests/...` path with no actual `cd`, which F0.5 confirmed
  fails empirically with `exit_code=4` (`no tests ran`) since the real runner
  never changes directory):**
  `uv run pytest shared/tests/test_cache_tree_compare_version_key.py shared/tests/test_ensure_shared_cache_walk.py shared/tests/test_ensure_shared_cache_ssot_pins.py shared/tests/test_plugin_cache_version_resolution.py shared/tests/test_ensure_shared_cache_vendored.py shared/tests/test_bloat_baseline.py shared/tests/test_bloat_defense_artifacts.py -v`
- **Evidence path:** `.shipwright/runs/iterate-2026-08-05-bloat-baseline-vendored-hook/surface_verification.json` — `exit_code=0`, `tests_run=138`, confirmed by actually executing it through F0.5 (not just documenting it).
