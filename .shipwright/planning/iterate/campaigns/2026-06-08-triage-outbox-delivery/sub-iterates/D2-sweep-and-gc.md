# Sub-Iterate: D2 — Iterate-setup sweep outbox->branch under full lock + delivered-line GC; drop integrate_main reconcile

## Scope

`setup_iterate_worktree`: after the worktree+branch exist, SWEEP the outbox -> append+dedup into the BRANCH `triage.jsonl`, commit on `iterate/<slug>` (B7-exempt), holding the canonical triage lock across the ENTIRE read->materialize section (Codex Q4 — data-loss blocker). GC: drop an outbox line ONLY once it is already present in the committed log (origin-delivered) -> abandoned/deleted branch keeps lines in the outbox, re-swept next iterate (no reset-after-read; Codex unlisted failure mode). Reuse the IDENTICAL EOL-normalize + dedup_triage_lines + validate_triage_text (Codex Q3). DROP integrate_main's `reconcile_main_triage` call (Codex Q1 — vestigial; the merge runs in the worktree, not main). Relegate `reconcile_main_triage` (commit-to-main) to a manual-CLI fallback only.

## Acceptance Criteria

- [ ] RED-first: a concurrent background-producer append DURING the sweep loses NO line (lock spans read->branch-commit)
- [ ] RED-first: an abandoned/deleted iterate branch strands NO line (survives in the outbox, re-swept next setup)
- [ ] No `chore(triage)` commit lands on local main during setup (delivery rides the branch)
- [ ] integrate_main no longer calls reconcile_main_triage; the worktree merge still succeeds
- [ ] swept lines are exactly-once after PR merge + merge=union (identical EOL/dedup/validate as reconcile)
- [ ] These tests MUST be EMPIRICAL, not mocked — the canonical FileLock and real git operations are exercised for real (D2V re-proves this independently and GATES D3).
