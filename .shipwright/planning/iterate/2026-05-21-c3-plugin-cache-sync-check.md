# Iterate Spec: C.3 — Plugin-cache sync check

- **Run ID:** iterate-2026-05-21-c3-plugin-cache-sync-check
- **Type:** feature
- **Complexity:** small
- **Status:** draft

## Goal

Close the artifact-polish plan's final iterate by adding a check
that detects drift between the local plugin-cache (`~/.claude/
plugins/cache/shipwright/<plugin>/<version>/`) and the repo HEAD.
CLAUDE.md's own "Iterates 7-11 had plugin-side fixes that silently
never took effect because `update-marketplace.sh` was skipped"
warning captures the recurring failure mode — solo dev edits a
plugin-side file in the monorepo, runs an iterate, and the runtime
keeps using the cached version unaware. A non-fatal WARN at the
right place makes this visible.

## Acceptance Criteria

- [ ] **AC-1** `scripts/check_plugin_cache_sync.py` exists, walks
  `<repo_root>/plugins/shipwright-*/` and compares against
  `<cache_root>/<plugin-name>/<latest-version>/` by SHA-256 per
  tracked file.

- [ ] **AC-2** Tracked-file filter: `.py | .md | .json | .sh | .ps1
  | .yml | .yaml`. Skipped dirs: `__pycache__`, `.git`, `.venv`,
  `venv`, `node_modules`, `.pytest_cache`, `dist`, `build`.

- [ ] **AC-3** When `~/.claude/plugins/cache/shipwright/` doesn't
  exist (typical in CI), the check no-ops with
  `status="cache_root_absent"` — never crashes.

- [ ] **AC-4** When the repo's `plugins/` dir is absent, returns
  `status="no_repo_plugins"` — also no-op friendly.

- [ ] **AC-5** Drift states tracked per plugin:
  - `ok` — every tracked file's SHA matches.
  - `not_in_cache` — repo has the plugin, cache doesn't.
  - `drift` — at least one tracked file differs (counts +
    surfaces top-5 paths via `sample`).

- [ ] **AC-6** Fail-soft default: WARN on stderr, exit 0 even when
  drift exists. `--strict` flag flips this to exit 1.

- [ ] **AC-7** `--json` mode emits the structured result as JSON on
  stdout (for programmatic consumers like the audit-detector or a
  future SessionStart hook).

- [ ] **AC-8** Per-plugin handling is isolated: an OSError reading
  one cache plugin's files doesn't crash the others (handled by
  `_walk_tracked_files`'s `OSError` return-empty defaults).

- [ ] **AC-9** Multiple version dirs under the same plugin in the
  cache → lexically-latest one wins (`0.2.0` over `0.1.0`).

- [ ] **AC-10** Cache files that don't exist in the repo (e.g. a
  cached lockfile the plugin once generated) are NOT counted as
  drift — drift signals "cache is behind repo", not "cache has
  extra".

- [ ] **AC-11** Non-`shipwright-` plugins under the repo's
  `plugins/` dir are ignored (e.g. an external plugin co-installed
  for testing).

## Out of scope

- **Auto-trigger sync** — the check is detective-only. If the
  operator wants to fix the drift, they run
  `scripts/update-marketplace.sh` manually. Automating the sync
  inside the check would have side effects this iterate doesn't
  want to gate on.

- **Per-version drift detail** — when the cache has multiple
  versions, only the lexically-latest is compared. Older cached
  versions don't matter for the "is runtime using current code?"
  question.

- **`.claude-plugin/plugin.json` semantic-version awareness** — we
  don't try to parse the version field; lexical sort is enough for
  the small set of versions the cache holds.

- **Triage emission** — the script writes WARN to stderr and
  emits structured JSON; piping that into the triage producer
  contract is deferred to a future iterate. The campaign's other
  producers (B.2 SBOM, B.3 test-evidence) didn't gate on a hook
  either.

- **SessionStart hook integration** — adding a hook that runs
  this check at every session start lands in a separate iterate;
  shipping the script + tests first is the cautious move.

## Implementation Notes

- The script is ~150 LOC including docstrings — slightly larger
  than the plan's "~50 LOC" estimate because of the test-friendly
  parameterization (`--repo-root`, `--cache-root`, `--json`,
  `--strict`) and the structured result dict. Still under 200.

- `check_sync(repo_root, cache_root)` is a pure function; `main`
  is the CLI wrapper. Tests exercise both surfaces.

- The SHA-256 comparison is deterministic — `mtime` would be
  unreliable (different filesystems, archive extraction, etc.).
  Hash-based check is the right precision for "are these files
  byte-identical?".

- `_TRACKED_SUFFIXES` deliberately omits binary types (`.pyc`,
  `.so`, `.png`) — those are build artifacts that legitimately
  differ between repo + cache without indicating drift.

## Verification

- `uv run --extra dev pytest shared/tests/test_plugin_cache_sync.py
  -v` — 14 new tests covering AC-1..AC-11.

- Full shared suite: 2155 passed (baseline 2141 + 14 new).

- Manual smoke (against this monorepo): `uv run
  scripts/check_plugin_cache_sync.py --json` runs successfully,
  reports per-plugin sync state vs the local
  `~/.claude/plugins/cache/shipwright/`.
