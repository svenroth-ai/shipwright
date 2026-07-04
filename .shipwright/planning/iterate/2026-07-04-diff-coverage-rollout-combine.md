# Iterate: diff-coverage Phase 2 — roll out `--cov` + combine across all plugins

- **run_id:** `iterate-2026-07-04-diff-coverage-rollout-combine`
- **Campaign:** `diff-coverage` (sub-iterate 2 of 4) · anchor `trg-8fdebda3`
- **Intent:** feature (repo-wide coverage measurement + W4 activation) · **Complexity:** medium
- **Risk flags (diff-driven, authoritative):** `touches_io_boundary`
  (creates `shipwright_test_config.json`, writes tracked `coverage.total`). NOT
  `cross_component` / `touches_build` — `.github/workflows/ci.yml` and
  `pyproject.toml` are in neither pattern list; verified against
  `risk_detectors.py`.
- **Spec Impact:** ADD (new repo-wide coverage-combine capability + W4 activation).

## Goal

Extend the Phase-1 shared-only measurement chain across the monorepo: every
plugin's Python source (`plugins/*/scripts/`) **that has a test suite**, plus
`shared/` plus `integration-tests`, contributes to **one combined, repo-relative
`coverage.xml`**. (Out of scope for the number: repo-root `scripts/` and any
plugin without a `tests/` dir — coverage requires executed tests; all 14 plugins
currently ship one.)
From that honest whole-repo number, populate the tracked
`shipwright_test_results.json.coverage.total` and light the dormant **W4** verifier
green via a calibrated `shipwright_test_config.json.coverage.min` baseline.
`coverage.diff` stays PR-local/transient. Still **no grade effect** (Phase 3) and
**no CI fail-gate** (Phase 4).

## The hard part (settled empirically — kickoff spike)

Each plugin suite runs `cd plugins/<name> && pytest` (its own uv env + `tests`
package). With `[tool.coverage.run] relative_files = true`, coverage records paths
**relative to the plugin CWD** — i.e. `scripts/lib/foo.py`, with the plugin
identity **lost** in the data file. A single global `coverage combine` `[paths]`
mapping **cannot** disambiguate N plugins that all record `scripts/...` (proven:
the wildcard `plugins/*/scripts/` mapping leaves them un-remapped → `coverage xml`
errors "No source for code").

**Winning mechanic (proven on a synthetic 2-plugin fixture):** remap **per
plugin**, one data file at a time, with a plugin-specific `[paths]`:

```
[paths]
src =
    plugins/<name>/scripts/     # canonical (repo-relative)
    scripts/                    # alias (what the plugin recorded)
```

`coverage combine --append <that-plugin's-datafile>` then rewrites `scripts/foo.py`
→ `plugins/<name>/scripts/foo.py` and accumulates into `.coverage`. `shared`/
`integration` data is already repo-relative (measured from repo root) → no remap.
`coverage xml` over the accumulated data emits the combined repo-relative report.

This per-plugin loop is encapsulated in a **tested tool** (`combine_coverage.py`)
rather than fragile inline CI bash — the combine logic is the real monorepo risk,
so it gets a synthetic-fixture unit test.

## Acceptance Criteria

- [ ] **AC1 — per-plugin `--cov`.** `ci.yml`'s plugin loop runs each plugin
      (that has a `scripts/` dir) with `--cov=scripts` + a per-plugin
      `COVERAGE_FILE` under a dedicated data dir. `shipwright-preview` (no
      `scripts/`) still runs tests, contributes no coverage. Integration + the
      three shared per-dir runs each record repo-relative source into their own
      data file.
- [ ] **AC2 — combined repo-relative report.** New
      `shared/scripts/tools/combine_coverage.py`: scans the data dir; for each
      `.coverage.<label>` file remaps per-plugin (`scripts/` →
      `plugins/<label>/scripts/`) or passes through `shared`/`integration`
      un-remapped; emits one combined `coverage.xml` whose `<class filename=...>`
      are **repo-relative** (`plugins/<name>/scripts/...`, `shared/...`), and
      prints the overall line-rate. Absent-input safe (no data → structured n/a,
      exit 0). Unit-tested with a synthetic 2-plugin fixture (the crux test):
      asserts repo-relative filenames + a correct blended line-rate.
- [ ] **AC3 — diff-cover over the combined report.** The `ci.yml` "Diff coverage
      (informational)" step consumes the **combined** `coverage.xml`. The `repo`
      tier label is carried by flipping `measure_diff_coverage.py`'s `DEFAULT_TIER`
      to `repo` (CI calls `uvx diff-cover` directly; the transient
      `.shipwright/coverage/diff_coverage.json` is written by the compliance flow,
      not CI). Still non-gating (`continue-on-error`, no `--fail-under`); allowlist
      entry stays valid.
- [ ] **AC4 — tracked repo-wide `coverage.total`.** New
      `shared/scripts/tools/record_coverage_total.py` parses the combined
      `coverage.xml` line-rate and writes `shipwright_test_results.json`
      **top-level** `coverage.total` (+ `measured_at`, `source`, `measured_tier`
      = `repo`) **atomically**, **preserving** `iterate_latest`. Measured once for
      this repo and committed.
- [ ] **AC5 — W4 lit green.** New tracked `shipwright_test_config.json` with
      `coverage.min` = a documented, calibrated anti-ratchet baseline strictly
      below the measured `coverage.total` (round floor with headroom for noise —
      NOT the measured number itself, NOT a value that hides a bad number).
      `check_w4_coverage_meets_threshold(project_root)` returns **PASS** on the
      committed files (was SKIP). Round-trip test: recorder writes total → W4
      reads it → PASS (the `touches_io_boundary` Boundary Probe).
- [ ] **AC6 — `.diff` still transient, grade still neutral.** `coverage.diff`
      never tracked. `compute_grade` output provably identical with/without a
      coverage report (Phase-1 invariant preserved). Dashboard INFO line renders
      the combined-repo tier label.
- [ ] **AC7 — `.gitignore`.** Broaden `.coverage` → `.coverage*` and cover the
      per-plugin data dir; `coverage.xml` + `.shipwright/coverage/` already
      covered.
- [ ] **AC8 — TDD + CI-convention tests.** combine tool (fixture + absent-safe +
      no tracked mutation); recorder (round-trip + iterate_latest preserved +
      atomic); W4-green; ci.yml conventions (per-plugin `--cov`, combine step,
      diff-cover over combined); allowlist stays green
      (`check_ci_gate_coverage.py`).

## Confidence Calibration
- **Boundaries touched:** `shipwright_test_config.json` (new, W4 threshold
  reader), `shipwright_test_results.json` top-level `coverage.total` (W4 value
  reader), the combined `coverage.xml` producer/consumer seam.
- **Empirical probes run:**
  1. Synthetic 2-plugin coverage-combine spike → per-plugin `[paths]` remap
     yields repo-relative `coverage.xml`; a single global/wildcard `[paths]`
     does NOT (leaves `scripts/...` → `coverage xml` "No source" error).
  2. Real recipe on one plugin (changelog) → `--cov-config=<root pyproject>`
     makes a `cd plugin` run record RELATIVE `scripts/...` (not absolute), and
     combine → `plugins/shipwright-changelog/scripts/...` (65% tier).
  3. **Full repo-wide measurement** (all 13 plugins + shared + integration, real
     suites, all green) → combined **80.2%** (25068/31274 lines); 0 files under a
     `tests/` dir / conftest / fixtures leaked (omit verified).
  4. W4 on the committed files → **PASS** `coverage.total=80.2% >= threshold=70%`
     (was SKIP).
- **Test Completeness Ledger:** every AC → `tested` (see `shipwright_test_results
  .json.iterate_latest.test_completeness`); 0 untested-testable.
- **Confidence-pattern check:** asymptote (combine tool depth: real-coverage
  fixture + absent-safe + idempotent + no tracked-file mutation) + breadth (CI
  wiring test, W4 round-trip, grade-neutrality, gitignore, baseline-lit invariant).
  No `cross_component` machinery → no integration-composition behavior required.

## Notes
- Post-merge: `scripts/update-marketplace.sh` (touches `shared/` +
  `plugins/shipwright-compliance`).
- Durability: top-level `coverage.total` is a tracked baseline refreshed by
  re-running `record_coverage_total.py`; F5 edits only `iterate_latest`.
