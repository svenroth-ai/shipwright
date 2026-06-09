# B6 — Docs + cross-plugin fan-out regression guard

- **Type:** change (docs + test)
- **Complexity:** small
- **Depends on:** B1–B5 (lands last, or stacked alongside each)

## Goal

Make the consolidation durable: update the single-source-of-truth docs and
add a regression test so the fan-out cannot silently creep back in.

## Acceptance Criteria

- [ ] **AC-1 (hooks registry).** `docs/hooks-and-pipeline.md` hooks
      registry + context-loading matrix + artifact-write matrix updated to
      reflect dispatcher-owned hooks (per the CLAUDE.md rule: any hook
      change MUST update this doc).
- [ ] **AC-2 (fan-out regression test).** A test that parses all 12
      `hooks.json` and asserts the consolidated invariant: the shared
      dispatcher scripts appear in **exactly one** plugin
      (`shipwright-iterate`), not N. Fails loudly if a future edit
      re-registers a shared hook across plugins.
- [ ] **AC-3 (cache-sync verification).** `update-marketplace.sh` +
      `check_plugin_cache_sync.py --strict` run clean; the runtime cache
      reflects the de-registered topology (cf. CLAUDE.md "When editing
      plugin-side files").
- [ ] **AC-4 (consumer back-compat doc).** A short migration note for
      end-user projects on older cached plugins.
- [ ] **AC-5 (guide check).** `docs/guide.md` ch. 8 (quality gates) /
      hooks references reconciled if affected.

## Tests

- The AC-2 parser test is the keystone deliverable here.

## Note

This is the anti-ratchet for the whole campaign: without AC-2, a later
"just add the hook to every plugin for safety" edit would silently restore
the 11×-fan-out the campaign removed.
