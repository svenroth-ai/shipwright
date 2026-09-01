# Published-package manifest sync

Reference for **Step 5.4** and **Step 6** of `/shipwright-changelog`.
Background: `.shipwright/planning/iterate/iterate-2026-08-11-changelog-manifest-version-sync.md`.

## Why this exists

Tagging a release and writing `CHANGELOG.md` says nothing about a published
package manifest (e.g. `bootstrapper/package.json`) — measured on a
downstream project: the tag and changelog said `0.24.0` while the manifest
that actually ships to a registry still said `0.23.0`. Nothing checked it at
release time or afterward. This closes that: a project declares which
manifests are published, the release writes the released version into each
in the same commit, and a fail-closed gate stops the release before it tags
if the write didn't actually land.

## Declaring published manifests

`shipwright_changelog_config.json` at the project root:

```json
{
  "published_manifests": [
    {"path": "bootstrapper/package.json", "format": "package_json"}
  ]
}
```

No file, no `published_manifests` key, or an empty list — all mean "no
manifests declared." The sync step is then a clean no-op: nothing is read,
written, or verified, and the release proceeds exactly as it did before this
mechanism existed. Two `format` values are implemented; any other value is a
named failure, not a silent skip:

- **`package_json`** — a single top-level `"version"` field (`package.json`,
  a plugin's own `.claude-plugin/plugin.json`, …).
- **`marketplace_json`** — a top-level `"version"` field AND a `"plugins"`
  array whose entries each carry their own `"version"` — a catalog manifest
  (`.claude-plugin/marketplace.json`) that names its own release version
  once and then repeats it per listed item. A release writes the SAME
  version into all of them together, never just the top-level field —
  that is what this format exists to close: this monorepo's own
  `marketplace.json` shipped v0.33.0 with every one of its 14 `plugins[]`
  entries still reading `0.32.0`, because nothing synced the nested field.

This monorepo declares its own 14 `plugins/*/.claude-plugin/plugin.json`
(`package_json`) plus its root `.claude-plugin/marketplace.json`
(`marketplace_json`) in its own `shipwright_changelog_config.json` — dogfood,
not just documentation.

**Operator precondition, not tool-checked:** this no-op is indistinguishable
from "the config exists but is gitignored in this checkout" — confirm
`shipwright_changelog_config.json` is actually tracked (`git ls-files
shipwright_changelog_config.json`, or `git check-ignore` returning nothing)
before relying on a clean run as proof nothing needed syncing.

## The two-call contract

**Step 5.4 — write + stage**, before Step 5.5 (compliance evidence) and well
before Step 6's commit:

```bash
uv run "{shared_root}/scripts/tools/sync_release_manifests.py" \
  --project-root . --version "{version}" --stage \
  --result-file ".shipwright/runtime/manifest_sync_result.json"
```

`status: "ok"` → fold `manifest_pathspec` from the JSON result into Step 6's
commit pathspec, alongside `evidence_pathspec`. **Anything else → stop, do
not tag** — same contract Step 5.5 already applies to compliance evidence.

Why this runs *before* Step 5.5, not between it and Step 6: a
worktree-modifying write landing in that gap is exactly the window Step 6's
own comment warns about (`git commit -- <paths>` reads the worktree, so a
writer between staging and commit substitutes bytes nothing re-checks).
Running 5.4 first keeps that gap free of a new writer.

**Step 6 — verify against the COMMITTED blob**, chained `&&` immediately
before `git tag`:

```bash
uv run "{shared_root}/scripts/tools/sync_release_manifests.py" \
  --project-root . --version "{version}" \
  --verify-commit "$(git rev-parse HEAD)" \
  --result-file ".shipwright/runtime/manifest_sync_result.json" \
  && git tag -a v{version} -m "Release v{version}"
```

**This is the pair that actually closes the card's regression** — verifying
the worktree alone (what an earlier draft of this design did) does not: if
the manifest write never made it into the release commit (an omitted
pathspec, a hand-edited commit command, anything), a worktree-only check
still sees the bumped file on disk and passes, while the tag ships over a
manifest that is, in the committed history, still at the old version.
`--verify-commit` reads the manifest from `git show <sha>:<path>` instead,
which can only say "ok" if the write is actually part of the commit being
tagged.

**Why `--verify-commit` reads `--result-file`, never the live config
again:** by the time the commit exists, `shipwright_changelog_config.json`
is mutable worktree state — edited, removed, or never itself committed. Re-
deriving the manifest list from it at verify time would let that mutation
silently change (or empty) what gets checked. `--result-file` freezes the
exact set Step 5.4 actually wrote and staged.

## Status vocabulary

| `status` | Meaning |
|---|---|
| `ok` | success — includes the no-manifests-declared no-op |
| `invalid_version_argument` | `--version` isn't a bare semver, or carries whitespace / a leading `v` |
| `invalid_config` | `shipwright_changelog_config.json` is malformed JSON or the wrong shape |
| `duplicate_manifest_path` | two declared entries canonicalize to the same file |
| `path_outside_project` | an absolute path or a `..` escape |
| `path_is_symlink` | any symlink component in the declared path — **in-root symlinks are refused too**, not just escaping ones: `git add` stages the symlink entry, not the resolved target's changed blob, so a write through an in-root symlink would let the worktree and the staged/committed content diverge |
| `manifest_missing` | the declared file doesn't exist |
| `manifest_dirty_before_sync` | the declared file already has uncommitted changes before this tool touched it — refusing to fold unrelated edits into the release commit via `--stage` |
| `unsupported_format` | `format` isn't `package_json` or `marketplace_json` |
| `invalid_manifest_structure` | (`marketplace_json` only) `"plugins"` is missing, isn't an array, or one of its entries isn't a JSON object |
| `parse_error` | the manifest isn't valid JSON |
| `missing_version_field` | no top-level `"version"` key (e.g. a `"private": true` workspace root) — never injected |
| `invalid_version_type` | `"version"` present but not a string |
| `ambiguous_manifest_structure` | duplicate top-level `"version"` keys — refuses to guess which one to rewrite |
| `write_failed` | an I/O error during the write phase (already-written manifests in this pass are restored) |
| `stage_failed` | `git add` failed after writes succeeded (already-written manifests are restored) |
| `verify_mismatch` | (verify-commit only) the committed blob's version doesn't match the release |
| `result_file_invalid` | (verify-commit only) `--result-file` is missing, unreadable, or malformed (not a JSON object, `manifests` not an array, or an entry missing `path`/`format`) |
| `sync_incomplete` | (verify-commit only) `--result-file` records a status other than `ok`, or records `dry_run: true` — a failed or dry-run Step 5.4 run's own output must never be trusted, even if the commit exists |
| `result_file_stale` | (verify-commit only) `--result-file` records a different `version` than the one being verified — a leftover from a prior release at the fixed, non-run-scoped path |

A relative `--result-file` resolves against `--project-root`, not the
process's working directory.

## What's out of scope, named rather than silently missing

- **`package-lock.json` / other lockfiles.** Only the manifest's own
  `version` field is synced. A project with a lockfile that also mirrors the
  root version (npm lockfileVersion 2/3 does, in two places) will still see
  it drift. Real scope creep beyond "package.json, the measured case" —
  not built here.
- **Publishing itself.** Whether/when/how the package reaches npm
  (`npm publish`, `NPM_TOKEN`) is a separate operator task.
- **Formats other than `package_json`/`marketplace_json`.** Any other value
  in `format` fails closed (`unsupported_format`) rather than a generic
  version-rewriting engine nobody has asked for yet.
- **A `marketplace_json` manifest whose `plugins[]` entries are already
  individually drifted from the top-level version at the START of a sync**
  is still written — the tool self-heals by forcing every entry to the
  released version — but the drift is not separately reported; only
  `reformatted: true` hints that the byte-preserving surgical path could
  not be used.
- **The `manifest_dirty_before_sync` guard, outside a git repo.** It reads
  `git status`, so a `--project-root` that isn't a git checkout at all (this
  tool's own unit-test fixtures, or a non-git project) sees no dirty-check
  at all rather than a forced failure — `/shipwright-changelog` itself always
  runs in a git repo, so this only matters for a caller outside that flow.

## Recovery

**Abort between Step 5.4 and the release commit** (Step 5.5 fails, the
session dies, anything): the worktree is left with a bumped, uncommitted
manifest. Re-run the release (idempotent — an already-current manifest
reports `changed: false` and is not rewritten), or `git checkout -- <path>`
to discard the bump. The standing check (below) catches the case where it
is later committed by accident.

**If byte-restoration itself fails** after a mid-sequence write or stage
failure (permission change, disk full mid-restore) — rare, and not
automatically recoverable further: the worktree may be left partially
modified. Manual recovery is the same `git checkout -- <path>`.

**On `stage_failed`**, the tool also unstages every declared path
(`git reset -q -- <paths>`) before restoring worktree bytes, so the index
cannot be left holding a partial `git add` while the worktree is rolled
back underneath it — defense-in-depth, since a bad pathspec (the one
preflight-reachable failure mode) already fails `git add` atomically with
nothing staged.

## The standing check

`changelog_checks.check_manifest_version_matches_tag`, run at Step 7,
compares every declared manifest's **committed (`HEAD`)** version against
the latest git tag — independent of whether Step 5.4/6 ran at all. It is
**`WARNING`, not `ERROR`**: the pre-tag `--verify-commit` gate above is what
actually blocks a release from tagging over a mismatch, so this check's only
job is surfacing drift the gate never saw — a release cut before this
mechanism existed, or a later commit hand-editing a manifest. A hard
release-blocking invariant here would also foreclose an intentional
post-release manifest edit, which is why Architecture Review descoped it
from `ERROR` during design.
