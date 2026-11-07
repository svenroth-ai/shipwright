# Mini-plan: S4 writers and finalization (dormant behind the flag)

Goal: one writer module for every event append, a live key-precedence function, drops-only format changes (run stamp, 16-hex ids, same-id dedup), lock outside the folder, rotate-on-commit with an ls-tree probe, F6 staging by own key, F11 committed-check after an ensure_current ABSORB, F7b seal, attach_commit as event_amended, validators/dedup ignoring the run stamp. Default layout stays legacy and its bytes are unchanged.

Steps
1. events_write.py (write_event_line, new_event_id, atomic create, dedup) and drop_key/implicit_key in events_layout.py.
2. record_event / finalize_iterate / convert_configs / adopt seeder route through it.
3. events_stage.py + stage_event_drops.py (F6), absorb in ensure_current, seal in commit_event_followup, drops_committed_state in the F11 verifier.
4. dedup_event_lines / event_context_index ignore the run member; carry-overs (OverflowError, latest_by_ts, atomic creation, KC8 wiring).
5. Prompts and docs; replay-gate known set emptied.

Risks: legacy byte drift (pinned by tests), concurrent writers (one lock per tree), git operations on shared worktrees (path-restricted, own keys only).
