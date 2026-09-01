# Mini-Plan: changelog-config-marketplace-sync

- **Run ID:** iterate-2026-09-01-changelog-config-marketplace-sync
- **Type:** feature (MODIFY of FR-01.09)
- **Complexity:** small

## Files to create/modify

| File | Change |
|---|---|
| `shipwright_changelog_config.json` (new, repo root) | declare the 14 `plugins/*/.claude-plugin/plugin.json` manifests (`package_json` format) plus `.claude-plugin/marketplace.json` (`marketplace_json` format) so `sync_release_manifests` stops being a no-op for this monorepo's own releases |
| `shared/scripts/lib/manifest_sync_core.py` | add `marketplace_json` to `SUPPORTED_FORMATS`; `read_manifest_version` delegates the format's `plugins`-array validation, `render_manifest_write` delegates its renderer, to the two new modules below (kept the file under the 300-line guideline) |
| `shared/scripts/lib/manifest_sync_marketplace.py` (new) | `validate_marketplace_structure` + `render_marketplace_write` — the marketplace-specific validation and renderer (surgical multi-occurrence substitution when root + every `plugins[].version` are already in lockstep, full JSON re-render self-heal fallback otherwise), split out of `manifest_sync_core.py` |
| `shared/scripts/lib/manifest_sync_errors.py` (new) | `ManifestSyncError` alone — a neutral leaf module (ADR-248 pattern) so `manifest_sync_core.py` and `manifest_sync_marketplace.py` can both import it without a cycle |
| `shared/scripts/tests/test_manifest_sync_core.py` | unchanged package_json coverage (marketplace_json tests moved out, see below) |
| `shared/scripts/tests/test_manifest_sync_core_marketplace.py` (new) | unit tests for the new format: read (happy path, missing/malformed `plugins`), render (surgical path, drifted-entry fallback path, byte preservation, round-trip) — split out to keep the original file under 300 lines |
| `shared/scripts/tools/tests/test_sync_release_manifests.py` | unchanged package_json orchestration coverage (marketplace test moved out) |
| `shared/scripts/tools/tests/test_sync_release_manifests_marketplace.py` (new) | `sync()`/`--dry-run`/`--stage` flow for a fixture declaring one `package_json` + one `marketplace_json` entry together |
| `shared/scripts/tools/tests/test_sync_release_manifests_git.py` | unchanged package_json `--verify-commit` coverage (marketplace test moved out) |
| `shared/scripts/tools/tests/test_sync_release_manifests_git_marketplace.py` (new) | `--verify-commit` coverage for a `marketplace_json` entry (committed-blob read) |
| `shared/tests/test_changelog_checks_manifest_sync.py` | confirm the existing `check_manifest_version_matches_tag` standing check works unchanged for `marketplace_json` (it's format-generic already — this is a coverage addition, not a code change) |
| `plugins/shipwright-changelog/skills/changelog/references/manifest-sync.md` | document the second format, its example config shape, and the new `invalid_manifest_structure` status code |
| `.shipwright/planning/01-adopted/spec.md` | FR-01.09 — one new AC (see Spec Impact) |

**Post-spec-review addendum:** the four new files above (`manifest_sync_marketplace.py`, `manifest_sync_errors.py`, `test_manifest_sync_core_marketplace.py`, plus the two `*_marketplace.py` test files) were not in the original plan — the Stop hook's bloat gate blocked completion on three files that crossed the 300-line guideline, so they were split after the fact. No behavior changed; `manifest_sync_core.__all__` still exports `ManifestSyncError` and every existing consumer's import path is unaffected.

**Post-code-review addendum (round 2):** the first code-review pass found two
Medium correctness bugs — both fixed, both re-verified clean by a second
code-review pass:

1. **Stranded-nested-entry blind spot.** The "is this manifest already
   current" check compared only the root `version`, so a `marketplace_json`
   manifest whose root matched the target but had a stale nested
   `plugins[]` entry was silently skipped by `sync()` and silently PASSED by
   both `verify_commit()` and `check_manifest_version_matches_tag()` — the
   exact regression class this iterate exists to close would sneak past the
   gate meant to catch it. Fixed with a new `describe_version_state(text,
   fmt, target_version) -> (matches, detail)` in `manifest_sync_core.py`,
   wired into all three call sites. `sync_release_manifests.py` grew past
   300 lines wiring it in, so `verify_commit()` was split out into a new
   `shared/scripts/tools/sync_release_manifests_verify.py`.
2. **No drift test for the config's own plugin roster.** Fixed with new
   `shared/tests/test_changelog_config_manifest_roster.py`, asserting the
   config's declared 14 `package_json` paths match
   `plugins/*/.claude-plugin/plugin.json` on disk and that
   `marketplace.json` is declared.

Three new regression tests exercise the bug class directly (root matches,
one nested entry stale):
`test_sync_still_writes_when_root_matches_but_a_plugin_entry_is_stale`,
`test_verify_commit_fails_when_root_matches_but_a_plugin_entry_is_stale`,
`test_marketplace_manifest_with_stale_plugin_entry_warns`.

**Final file list**, superseding the table above: add
`shared/scripts/lib/manifest_sync_paths.py` (path/config-loading primitives
split out of `manifest_sync_core.py`, same 300-line-guideline reason —
re-exported so `sync_release_manifests.py` and `changelog_checks.py`'s
existing imports are unaffected) and
`shared/scripts/tools/sync_release_manifests_verify.py` (new, `verify_commit`
split out of `sync_release_manifests.py`).

**Not touched:** the underlying `sync()`/`verify_commit()` *orchestration*
shape — both already dispatch to `manifest_sync_core` generically per
declared `format`; only the "is this current" comparison inside them
changed (see addendum above).

## Data model changes

None (no database/RLS).

## Test strategy

- `shared/scripts/tests/test_manifest_sync_core.py` — unit-level, both new
  functions, both formats' interaction.
- `shared/scripts/tools/tests/test_sync_release_manifests.py` /
  `..._git.py` — integration-level, through the CLI entry points, on
  fixture project roots (never the live monorepo — see
  `feedback_never_run_a_producer_to_verify_it`).
- **Boundary Probe (touches_io_boundary):** a real round-trip test —
  write a version via `sync()`, read it back via `read_manifest_version`,
  assert equality — for the new `marketplace_json` format specifically,
  since that is the new producer/consumer pair this iterate adds.
- No E2E/browser layer (no UI, no `dev_url`).

## Spec Impact

- **Classification:** MODIFY
- **FR:** FR-01.09 (`/shipwright-changelog`) — the manifest-sync AC already
  covers single-version-field manifests; this adds the multi-occurrence
  (top-level + catalog-entries) case as a new AC line under the same FR
  (FOLD, not MINT — same capability, wider manifest shape).

## Confidence Calibration

(Small complexity + `touches_io_boundary` risk flag — Safety-enforced, not
Mandatory; recorded here rather than in an iterate spec since Step 1 is
skipped at small.)

- **Boundaries touched:** `shipwright_changelog_config.json` (project
  config, read by `load_declared_manifests`) and every declared manifest —
  producer: `sync_release_manifests.py sync()` /
  `render_manifest_write()`; consumer: `read_manifest_version()`,
  independently exercised again by `changelog_checks.check_manifest_version_matches_tag`.
- **Empirical probes run:** `sync_release_manifests.py --project-root .
  --version 0.33.1 --dry-run` against the real 14 plugin.json +
  marketplace.json this run declares — `status: ok`, all 15 entries
  recognized, all report `changed: false` (already at 0.33.1). Re-ran with
  `--version 0.33.2` — all 15 report `changed: true`, `git status` confirmed
  zero files on disk actually touched (dry-run). Both prove the config's
  paths/formats resolve against the real repo, not just fixtures.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | `read_manifest_version` returns the top-level version for a well-formed `marketplace_json` manifest | tested | `test_read_marketplace_version_happy_path` PASSED |
  | 2 | rejects a `marketplace_json` manifest with no `plugins` key | tested | `test_read_marketplace_version_missing_plugins_key` PASSED |
  | 3 | rejects `plugins` that isn't a JSON array | tested | `test_read_marketplace_version_plugins_not_a_list` PASSED |
  | 4 | rejects a `plugins[]` entry that isn't a JSON object | tested | `test_read_marketplace_version_plugin_entry_not_an_object` PASSED |
  | 5 | still requires the top-level `version` field for `marketplace_json` | tested | `test_read_marketplace_version_missing_top_level_version` PASSED |
  | 6 | accepts an empty `plugins` list (degenerate but legal) | tested | `test_read_marketplace_version_empty_plugins_list_ok` PASSED |
  | 7 | `render_manifest_write` bumps root + every `plugins[].version` via the byte-preserving surgical path when all entries are in lockstep | tested | `test_render_marketplace_write_surgical_when_all_in_lockstep` PASSED |
  | 8 | self-heals (full JSON re-render) when a `plugins[]` entry has already drifted from `current_version` | tested | `test_render_marketplace_write_drifted_entry_falls_back_to_full_render` PASSED |
  | 9 | round-trip: a written `marketplace_json` reads back consistently (root + every plugin entry) | tested | `test_render_marketplace_write_round_trips_through_read` PASSED |
  | 10 | `sync()` orchestrates one `package_json` + one `marketplace_json` entry declared together in one config | tested | `test_sync_marketplace_manifest_bumps_root_and_nested_entries` PASSED |
  | 11 | `verify_commit` reads a `marketplace_json`'s COMMITTED blob correctly (root + nested) | tested | `test_verify_commit_passes_marketplace_json_when_write_landed_in_commit` PASSED |
  | 12 | the standing drift check (`check_manifest_version_matches_tag`) works unchanged for `marketplace_json` | tested | `test_matching_marketplace_manifest_passes` PASSED |
  | 13 | this monorepo's own new config (14 `plugin.json` + `marketplace.json`) resolves against the real files | tested | empirical dry-run probe above, `status: ok`, 15/15 entries |
  | 14 | `sync()` still writes (self-heals) a manifest whose root matches the target but has a stale nested `plugins[]` entry | tested | `test_sync_still_writes_when_root_matches_but_a_plugin_entry_is_stale` PASSED |
  | 15 | `verify_commit` fails (`verify_mismatch`) on a committed blob with root matching but a nested entry stale | tested | `test_verify_commit_fails_when_root_matches_but_a_plugin_entry_is_stale` PASSED |
  | 16 | the standing check (`check_manifest_version_matches_tag`) warns on root-matches-but-nested-stale | tested | `test_marketplace_manifest_with_stale_plugin_entry_warns` PASSED |
  | 17 | this monorepo's declared `package_json` roster equals the real `plugins/*/.claude-plugin/plugin.json` files on disk, and `marketplace.json` is declared | tested | `test_every_plugin_json_on_disk_is_declared`, `test_marketplace_json_is_declared_with_the_marketplace_format` PASSED |

  0 untested-testable.

- **Confidence-pattern check:** Asymptote (depth) — self-review's own
  "are you confident?" pass surfaced a real finding (three test files over
  the 300-line guideline); acted on it (split the largest one) rather than
  accepting the first "yes", per one additional probe before F0. Coverage
  (breadth): every ledger row `tested`, 0 rows `untestable`.
