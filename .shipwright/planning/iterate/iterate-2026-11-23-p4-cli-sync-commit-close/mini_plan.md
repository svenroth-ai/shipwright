# Mini-plan: P4 release CLI part 2 (sync, commit-and-tag, record-event, close-phase)

Goal: move the mechanical shell chains of SKILL.md Steps 5.3-7 of /shipwright-changelog into release.py subcommands (code), keeping outward commands (gh pr create/merge, tag push, release page) literal.
Approach: one lib module per subcommand behind an injected-runner seam (release_sync/commit/event/close/verify), two subprocess scripts for shared helpers (verify_release_tag.py, restore_derived.py), a run-state file in the git directory. Operator decisions F1a/F1b/F4/F6/F10/F7 are encoded in the flow; golden harness (frozen) gets approved deltas; CLI driver drives the frozen scenarios.
Tests: L1 injected-runner tests, real-git tests, golden scenarios through both drivers, seeded regression through the CLI driver.
Risks: frozen-file deltas, plugin-local lib package shadowing shared lib, phase_history writer kept in pipeline mode.
