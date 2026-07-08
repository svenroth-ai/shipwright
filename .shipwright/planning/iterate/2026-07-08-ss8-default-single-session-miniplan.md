# Mini-Plan — SS8 default-flip to single-session

## Chosen approach

**Separate the two conflated concerns** behind `DEFAULT_RUN_MODE`:
- `DEFAULT_RUN_MODE = "single_session"` → what a FRESH run gets.
- new `LEGACY_FALLBACK_MODE = "multi_session"` → how `config_io.run_mode` reads a
  mode-less/unrecognized config.

Then sweep the prose/docs/tests that documented the old default, add a migration
guide, and mark multi-session deprecated (code retained). Multi-session stays
functional (lifecycle is mode-agnostic) so no integration test breaks.

## Why this shape

- **Explicit migration, not silent reinterpretation.** Keeping the legacy read
  fallback at multi_session means an existing in-flight run is NOT reinterpreted
  the moment the default flips — the one user migrates deliberately (flip + resume),
  exactly the model in the migration guide. This is the safe, honest separation.
- **Deprecate, don't delete.** Removing the multi-session engine (load-bearing
  cross-plugin hooks) is a separate, riskier effort → deferred to `trg-0e8e7f90`.

## Alternative considered — rejected

- **Flip `DEFAULT_RUN_MODE` wholesale (one constant for both).** Rejected: it
  silently reinterprets every mode-less/legacy config as single-session mid-flight,
  breaks the explicit-migration contract, and would force weakening the SS5
  back-compat tests (which assert mode-less → multi_session). Fix the design, not
  the tests.

## Risk / rollback

- Behavior change (fresh default), but multi-session remains selectable and
  lifecycle-compatible → low blast radius; rollback = revert the PR.
- Verified: 75 plugin mode tests + 184 integration tests green under the flip.
