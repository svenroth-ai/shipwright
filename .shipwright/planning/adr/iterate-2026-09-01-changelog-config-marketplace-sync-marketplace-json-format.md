# ADR: dogfood release-manifest sync + marketplace_json format

## Context

The monorepo had no `shipwright_changelog_config.json`, so `sync_release_manifests.py`
was a no-op at release time: the 14 `plugins/*/.claude-plugin/plugin.json` +
`.claude-plugin/marketplace.json` version stamps were never bumped
automatically. v0.33.0 shipped with every plugin stranded at the prior
version (existing installs never detected the update); corrected by hand in
v0.33.1. `marketplace.json` also carries its version twice — once at the top
level, once inside each `plugins[]` catalog entry — a shape the existing
`package_json` format (single top-level field) cannot represent.

## Decision

Add `shipwright_changelog_config.json` declaring all 14 plugin.json
manifests (`package_json`, pre-existing format) plus `marketplace.json`
under a new `marketplace_json` format. `render_marketplace_write` bumps the
root version and every `plugins[].version` entry together in one write pass
(byte-preserving surgical substitution when already in lockstep, full JSON
re-render self-heal otherwise). A new `describe_version_state()` closes a
bug the first code-review pass found: comparing only the root version let a
manifest with a matching root but a stale nested entry be silently skipped
by `sync()` and silently passed by both `verify_commit()` and the standing
drift check — the exact regression this iterate exists to close. It is now
wired into all three call sites, with regression tests and a drift test
tying the config's declared roster to the real `plugin.json` files on disk.

## Consequences

Every future monorepo release automatically keeps all 15 manifests in
lockstep with the release tag; the v0.33.0-class regression cannot recur
silently. `sync_release_manifests.py` and `changelog_checks.py` grew a new
dependency on `manifest_sync_core.describe_version_state()`;
`manifest_sync_core.py`, `manifest_sync_marketplace.py`,
`manifest_sync_errors.py`, `manifest_sync_paths.py`,
`sync_release_manifests.py`, and `sync_release_manifests_verify.py` are now
six small cooperating modules instead of two, each under the 300-line
guideline.

## Rationale

A root-only comparison is the natural first implementation and passed the
initial review; a second code-review pass specifically re-verifying the fix
(not just re-scanning for new issues) is what caught that the bug class
could still slip past the release gate itself, not just the write path — so
the fix had to reach `describe_version_state`, not just
`render_marketplace_write`.

## Rejected

Considered comparing only `render_marketplace_write`'s own lockstep check
and leaving `sync()`/`verify_commit()`/the standing check on a root-only
comparison — rejected because that leaves the release gate itself blind to
the exact drift class the format exists to catch.
