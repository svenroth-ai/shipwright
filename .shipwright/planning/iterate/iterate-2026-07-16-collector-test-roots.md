# Iterate ADR — Config-driven `test_roots` for the `test_links` collector

- **Run-ID:** iterate-2026-07-16-collector-test-roots
- **Standalone iterate** (NOT a campaign). Traceability follow-on unblocker.
- **Complexity:** medium · **change_type:** feature · **spec_impact:** none (framework tooling)
- **Covers gap:** `plugins/*/tests` + `shared/tests` were OUT of the collector's scan scope, so
  an `@FR` tag written into a plugin/shared test would write-then-drop (never reach the
  regenerated manifest). ~187 confident tag candidates are stranded behind this. This iterate
  makes the roots project-configurable so those tests become scannable; the actual tag backfill
  is a separate follow-up data-run.

## Problem statement + alternatives considered

`test_links.generate_file` scanned only `_test_links_io.default_test_roots()` = root-level dirs
in `_DEFAULT_TEST_DIRS`. A tag under `plugins/shipwright-x/tests/` never reached the manifest.

- **Alt A (rejected): hardcode `plugins/` into the shared collector.** Violates the "no repo
  layout in shared code" rule — every generic downstream project would inherit a monorepo-specific
  scan. Rejected.
- **Alt B (rejected): a whole-repo `rglob` walk.** Re-introduces the O(all-files) descent hang the
  TT7 adopt work already fixed (materializes+sorts a committed `node_modules`). Rejected.
- **Chosen: project-configurable `test_roots`.** Read an optional `traceability.test_roots` list
  from `shipwright_compliance_config.json`. ABSENT ⇒ exactly the historical `_DEFAULT_TEST_DIRS`
  (zero change for every existing project + the frozen fixtures). PRESENT ⇒ exactly those roots
  (dir names or fixed-depth globs like `plugins/*/tests`). The monorepo opts its own layout in via
  config. Traversal rewritten to `os.walk` + in-place `dirnames[:]` prune (the TT7 pattern) so a
  vendored subtree is never descended into.

## Design

1. `_test_links_io.configured_test_roots(root)` — resolves `traceability.test_roots` (globs via
   `Path.glob`, fixed-depth; `**` dropped to avoid re-opening the descent hang; existing dirs only;
   sorted + de-duped). Absent/malformed/empty ⇒ `default_test_roots` (fail-soft).
2. `_test_links_io.configured_prune_dirs(root)` — `_PRUNE_DIRS ∪ traceability.exclude_dirs`. The
   monorepo excludes `fixtures` so the collector's OWN traceability mini-repos (which carry
   deliberately fake `@FR` tags) never fan a bogus orphan into the real manifest.
3. `iter_test_files(roots, base, prune_dirs=_PRUNE_DIRS)` — rewritten from `rglob` to `os.walk`
   with in-place `dirnames[:]` prune. Files collected + sorted per-root ⇒ byte-identical order to
   the prior scan for any prune-free tree (golden stays green).
4. `build_manifest(..., prune_dirs=None)` + `generate_file` thread the config through.
5. `_suite_tags.propagate_suite_tags` gated to TS/JS suffixes — describe/it suites are a TS/JS-only
   construct, so a `describe(...)`/`it(...)` appearing inside a PYTHON string literal (exactly what
   the traceability self-tests embed as data) is no longer mistaken for a real suite tag. This was
   a latent bug the module docstring already ASSUMED away ("`.py` sources produce nothing"); the
   expanded scan surfaced it (5 phantom orphans from one collector self-test). The gate makes the
   documented contract real.
6. Monorepo `shipwright_compliance_config.json` gains `traceability.test_roots` (existing roots +
   `plugins/*/tests` + `shared/tests`) and `traceability.exclude_dirs: ["fixtures"]`.

## Guardrails honored

- Frozen P1 manifest-v2 schema UNCHANGED (additive — more roots scanned, no schema edit).
- `test_traceability_golden_consistency.py` + collector/hardening golden tests stay green
  (default path unchanged; suite gate is a no-op for the golden `.ts` fixtures).
- TT2 `group_d` (D-orphan/D-layer) + TT5 `layer_coverage` gates: regenerated monorepo manifest is
  clean (15 reqs, 0 orphans, 0 invalid, schema-valid; untagged 158→7014 — expected, honest).
- ADR-045 lib discipline unchanged; all touched files ≤300 LOC (225/267/93 + a 202-LOC test);
  bloat baseline NOT ratcheted.

## Scope

Collector-scope enablement + the monorepo config opt-in ONLY. The 187 plugin tags are NOT
bulk-written here (separate backfill data-run). Capability proven by an integration behavior:
a plugin-dir tagged test round-trips into the on-disk manifest, and a fixture poison tag is fenced.

### Deferred: the expanded monorepo manifest is NOT committed here

Regenerating `.shipwright/compliance/test-traceability.json` with the opt-in expands it from 158
to ~7014 untagged entries (clean: 0 orphans, 0 invalid, schema-valid). It is deliberately **left
at its pre-change state** in this PR for two reasons: (1) keeps the diff focused on the collector +
config + tests (a ~6.9k-line generated-data churn would dominate review); (2) the manifest now
contains thousands of `plugins/shipwright-compliance/tests/...` test-id strings, which the
`artifact-path-canon` Layer-1 lint FALSE-flags (its `(?<![\w/.\\])compliance/` regex does not
exclude the `-` in `shipwright-compliance/`). Committing the expanded manifest is the natural job
of the tag-backfill iterate, which will also carry the canon allowlist / regex fix for the manifest
artifact. No gate depends on a fresh committed manifest: F1 does not compare it, `group_d` reads the
still-valid committed one, and TT5 regenerates base+head itself (R3). The other finalize-regenerated
compliance MDs (RTM, test-evidence, dashboard, …) do NOT embed plugin test-ids and are committed.

## External-Plan-Review-Findings (Step 3.5 — Gemini 3.1 Pro + GPT-5.4 via OpenRouter, both succeeded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| O1 | High | "Present-but-empty/malformed `test_roots` silently falls back to defaults — presence must be authoritative." | **accepted-and-fixed** — refactored `configured_test_roots`: ABSENT key → default; PRESENT list → used exactly (each valid entry resolved, even resolving to zero dirs); non-list value → default WITH a stderr diagnostic (never silent). New tests `test_present_list_is_authoritative_even_when_it_resolves_to_nothing` + `test_wrong_type_test_roots_falls_back_to_default`. |
| O2 / G3 | Med/Low | "Root/glob resolution can escape the workspace (`../`, absolute, symlink)." | **accepted-and-fixed** — each match is `resolve()`d and dropped unless `is_relative_to(project_root)`; `os.walk` runs `followlinks=False` (default, now commented). `Path.glob` already rejects absolute patterns. New test `test_config_root_escaping_the_project_is_dropped`. |
| O3 | Med | "Overlapping roots (`tests` + `tests/unit`) could double-scan / reorder." | **accepted-and-fixed (already handled, now pinned)** — `iter_test_files` de-dups by absolute path across roots; roots de-dup by resolved path. New test `test_overlapping_roots_yield_each_file_once`. |
| O6 | Med | "Suite-tag suffix gate introduces a SECOND suffix list that can drift." | **accepted-and-fixed** — gate now reuses the frozen grammar's OWN `_TS_SUFFIXES` (the single authoritative vocabulary, identical to what the collector scans), not a local copy. |
| G1 | Med | "`os.walk` yields arbitrary order; sort for determinism." | **accepted-and-fixed** — `dirnames[:] = sorted(...)` in-place (deterministic descent) AND the collected file list is sorted per-root (deterministic yield). Golden stays byte-identical. |
| O4 | Med | "`exclude_dirs` is a new, broad (basename-at-any-depth) config contract not in the ask." | **accepted-with-reason** — it is REQUIRED to make the opt-in usable: the collector's own traceability mini-repos live under real (non-fixture-excludable-by-root) `plugins/*/tests` and carry fake `@FR` tags; only a dir-name prune (matching the existing `_PRUNE_DIRS` semantics) fences them without dropping the plugin's real tests. Basename-at-any-depth is intentional + documented; it is opt-in (absent ⇒ exactly `_PRUNE_DIRS`). |
| O1b / G4 | High/Low | "Silently dropping `**` globs is confusing; fail-fast or warn." | **partially-accepted** — a `**` ENTRY is skipped (not mutated), other entries in the list are still honored; a fully-`**` list resolves to `[]` (present⇒exact, visibly empty — not a silent default). `**` is refused because `Path.glob('**/…')` root-resolution descends a vendored tree (the exact hang this iterate removes). Documented in the docstring. New test `test_recursive_glob_entry_is_skipped_others_kept`. |
| G2 | Low | "Verify a JSON schema for `shipwright_compliance_config.json` isn't broken." | **rejected-with-reason** — there is NO schema for that config (only run_config/decision_drop/triage_item schemas exist); it is read loosely (`thresholds.py` pattern). Two optional arrays under a new `traceability` block break nothing. |
| — | — | Overall: both reviewers rated the config-driven-opt-in + `os.walk`-prune approach "sound/defensible" and praised catching the latent Python-AST/suite bug. | noted |

## External-Code-Review-Findings (Step 3.7 — Gemini + GPT-5.4 via OpenRouter; both succeeded, Gemini output truncated)

Diff reviewed: the 5 source/config/test files (the ~7k-line regenerated monorepo manifest was
excluded from the review diff as generated data — reviewing it line-by-line adds no signal).

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| C1 | Med | `_read_traceability_config` calls `config.get(...)` assuming a dict — a valid-JSON-but-non-object root (`[]` / `"x"` / `null`) raises `AttributeError` and aborts the regen. | **accepted-and-fixed** — added `if not isinstance(config, dict): return {}`. Regression: `test_non_object_config_root_does_not_crash`. |
| C2 | Med | `project_root.glob(entry)` runs BEFORE the containment check; an absolute `test_roots` entry makes `Path.glob` raise, so the documented "dropped" never happens — the regen crashes. | **accepted-and-fixed** — the glob is wrapped in `try/except (ValueError, NotImplementedError, OSError)` → the entry is skipped, never crashes. Regression: `test_absolute_test_root_entry_is_dropped_not_crashed`. |
| C3 | Med | "No integration test proves the cross-component round-trip / absent-config / glob / pruning behavior." | **accepted-clarified (already satisfied)** — the reviewer saw only `git diff HEAD`, which omits the NEW (untracked) test module; the tests DO exist: `test_plugin_dir_tagged_test_round_trips_and_fixtures_are_fenced` (integration), `test_configured_roots_default_to_conventional_when_absent`, `test_glob_roots_resolve_to_existing_plugin_dirs`, `test_overlapping_roots_yield_each_file_once`. They ship in the commit. |
| C-Gemini | — | Truncated mid-analysis (root itself named `node_modules` is not pruned since it is the walk start). | **reviewed — no actionable defect**: a root is EXPLICITLY opted-in via config, so not pruning the root itself is correct (the reviewer reached the same conclusion before truncating). |

Overall: GPT rated **ship-with-fixes**; both robustness fixes applied + pinned.

## Internal review cascade (delegated to orchestrator)

Runner has no `Agent` tool; the `spec-reviewer` → `code-reviewer` → `doubt-reviewer` cascade is
delegated to the campaign/standalone orchestrator. `reviews.code.status = delegated_to_orchestrator`.

## Self-Review (Step 3.6 — canonical 7-item checklist)

1. **Spec Compliance** — PASS. Config-driven `traceability.test_roots` (absent→default,
   present→exact), `os.walk`+in-place-prune traversal, monorepo opt-in (`plugins/*/tests` +
   `shared/tests` + `exclude_dirs:["fixtures"]`). Frozen v2 schema untouched. Golden green. Scope
   held to enablement — no bulk tag backfill.
2. **Error Handling** — PASS. Unreadable/garbled config → caught (`JSONDecodeError`/`OSError`) → `{}`
   → default; wrong-type `test_roots` → stderr diagnostic + default; missing dirs skipped
   (`is_dir` guard); test files read `errors="ignore"`; the `prune_dirs or io._PRUNE_DIRS`
   fallback keeps `build_manifest` callers that pass nothing unchanged.
3. **Security Basics** — PASS. Configured roots are containment-checked (`resolve()` +
   `is_relative_to(project_root)`), so an absolute/`..`/symlink escape is dropped; `os.walk`
   runs `followlinks=False`; sources are parsed as TEXT/AST (never imported/executed); output is
   JSON data. `Path.glob` rejects absolute patterns; `**` refused (descent-hang guard).
4. **Test Quality** — PASS. 13 tests: default preservation (key absent / block-present-no-key /
   malformed-BOM / wrong-type), present-authoritative-resolves-to-zero, glob resolution,
   `**`-entry-skip, path-escape containment, `exclude_dirs` prune, overlapping-roots single-yield,
   embedded-TS-in-Python suite-gate regression, and TWO `@pytest.mark.integration` round-trips
   (plugin-dir tag reaches the on-disk manifest + fixture fence; exclude proven load-bearing).
5. **Performance Basics** — PASS. `os.walk` + in-place `dirnames[:]` prune → a vendored subtree
   is NEVER descended (removes the rglob materialize+sort hang the expanded scan would worsen);
   glob root-resolution is fixed-depth (`**` refused). Real monorepo probe: 16 roots, sub-second.
6. **Naming & Structure** — PASS. `configured_test_roots` / `configured_prune_dirs` /
   `_read_traceability_config` cohesive; config threaded via a single `prune_dirs` kwarg; the
   suite gate reuses the grammar's authoritative `_TS_SUFFIXES` (no duplicated vocabulary). All
   touched files ≤300 LOC (234/267/93 + a 217-LOC test); baseline not ratcheted.
7. **Affected Boundaries (ADR-024)** — PASS. NEW producer/consumer identified: the human-edited
   `shipwright_compliance_config.json` `traceability` block is a new serialized-format INPUT the
   collector consumes; the manifest + `group_d`/`layer_coverage` gates are the downstream
   consumers. Real round-trip probe run (config→collector→file→schema-validate→reload) — see
   Confidence Calibration; the real-monorepo regen probe caught + fixed a phantom-orphan bug.

## Confidence Calibration (Step 3.8 — empirical probes, asymptote heuristic)

Boundaries touched (ADR-024): (a) the human-edited `shipwright_compliance_config.json`
`traceability` block → collector (a NEW serialized-format input); (b) the producer→file→consumer
manifest round-trip; (c) the filesystem scan (`os.walk`).

- **Probes run (11):**
  1. Real-monorepo regen (16 roots) → **found 5 phantom orphans** from `propagate_suite_tags`
     matching `describe`/`it` inside PYTHON string literals (the collector's own self-tests) →
     **fixed** (TS/JS suffix gate) → re-regen clean (0 orphans).
  2. Clean round-trip (config→plugin-dir tag→file→schema-validate→reload): link present, orphans 0.
  3. UTF-8 BOM config → fail-soft to default + **stderr diagnostic** (fix added after this probe
     showed a SILENT disable), no crash.
  4. CRLF config → parsed, link present (JSON allows CRLF whitespace).
  5. Non-object JSON root (`[]`) → no `AttributeError` (code-review C1 fix), default fallback.
  6. Absolute `test_roots` entry → dropped, no `Path.glob` crash (code-review C2 fix); the
     sibling relative entry still resolves.
  7. Garbled JSON → fail-soft + diagnostic, no crash.
  8. Present empty `test_roots: []` → exact (empty scan), not a silent default.
  9. `../outside` escape → containment-dropped (`is_relative_to`).
  10. Overlapping roots (`tests` + `tests/unit`) → each file yielded once (abs-path dedup).
  11. `fixtures` exclude on/off → poison tag fenced / would-orphan (exclude proven load-bearing).
- **Findings → fixes:** probe 1 (phantom orphans → suffix gate), probe 3 (silent disable →
  diagnostic); code-review C1/C2 (crash-on-malformed → guards) re-probed clean at 5/6/7. Two+
  consecutive clean probe rounds after the last fix ⇒ **asymptote reached; boundaries calibrated.**
- **Edge cases not probed (acceptable):** a `**` glob is refused by contract (documented; would
  re-open the descent hang); `exclude_dirs` basename-at-any-depth could prune a legitimately-named
  `fixtures/` test dir — intentional opt-in, the monorepo has none; duplicate leaf test ids across
  roots collide on `path::name` (same identity contract as the frozen grammar/TT1 — no new
  divergence); non-ASCII/whitespace spec-table cells were calibrated by TT1 (unchanged here).

### Post-build doubt-review fix round (orchestrator adversarial cascade)

The spec/code/doubt cascade on the built PR surfaced one HIGH must-fix that the runner's
own GPT+Gemini review missed — a latent CI time-bomb, exactly the false-green class this
traceability campaign exists to catch:

- **Finding (doubt HIGH):** committing the monorepo `traceability` opt-in makes the config
  LIVE, but `update_compliance` regenerates + commits `test-traceability.json` on EVERY
  iterate finalize. The regenerated manifest renders ~1000 `plugins/shipwright-compliance/
  tests/...` ids whose `-compliance/` segment false-matches the `compliance` migration's
  canon regex (`-` absent from the negative-lookbehind) — so the NEXT *unrelated* iterate's
  `test_artifact_path_canon` gate would go red on an artifact it never touched.
- **Fix:** allowlist `.shipwright/compliance/test-traceability.json` in all four migration
  allowlists (same generated-churn-artifact class as `change-history.md`), + a regression
  (`shared/tests/test_artifact_path_canon_manifest_allowlist.py`) proving the FP is real
  (non-vacuous) and the manifest is exempt everywhere.
- **Probe 12 (empirical proof):** wrote the real expanded 7024-entry manifest (0 orphans,
  schema-valid) to the tracked path and ran the canon lint → GREEN via the allowlist (1068
  `-compliance/` hits all exempt); restored the committed manifest.
- **LOW-4 hardening (doubt):** the wider `os.walk` scan could list a dangling `test_*.py`
  symlink whose `read_text` (`errors='ignore'` swallows only decode errors) would crash the
  regen → added an `is_file()` guard in `iter_test_files` + a POSIX-CI-exercised regression.
- **MEDIUM carried forward (NOT this iterate):** the TT5 enforcing regen
  (`_layer_coverage_regen._build`) uses `default_test_roots` and stays config-blind, so
  plugin/shared coverage is RTM-visibility-only until a follow-up threads the config in
  (handling the base-side config asymmetry). No effect here — no plugin tags exist yet, so
  the RTM and the gate agree. Recorded for the tag-backfill iterate.

The expanded manifest is intentionally NOT committed here (it regenerates naturally and
would fan a churn-conflict cascade across the concurrent iterate worktrees); the canon fix
keeps every future auto-regen green.

## Risk-flag note

First classifier run returned `large` with `prior_source=keyword` + `touches_migrations` — the
documented prose-keyword false-positive class (the verbose plan message inflated scope; nothing
touches SQL/migrations). A neutral, diff-accurate re-run returned `medium` (history prior, n=20),
`scope_keyword_estimate=trivial`, zero risk flags. Proceeded as medium (correctly triggers the full
review cascade + confidence calibration). Real flags: `cross_component` (collector machinery) +
`touches_io_boundary` (filesystem walk + config read). F11 recomputes from diff-predicates.
