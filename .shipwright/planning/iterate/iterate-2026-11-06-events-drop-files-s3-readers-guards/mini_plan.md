# Mini-plan: events-drop-files S3 (readers, aliases, classifiers, guards)

Goal: every reader of the event log goes through the assembling reader (legacy + archive + drops), every
path classifier lists the three folders, a reference guard fails on any unclassified mention of the log
name, and the read-side absence gates use the KC8 primitive. Layout stays dormant (default legacy); legacy
bytes and behaviour unchanged.

Steps:
1. events_read: sentinel-safe sibling loading, OverflowError, vanished-drop fail-closed (S2 follow-ups); read_events_at/events_text/event_lines_at.
2. Migrate readers (config, spec_chain, phase_quality, verifiers, stop guard, backfill, fr_history, affected_acs, compliance, grade, test, adopt).
3. Migrate ensure_current reconcile (churn_events), campaign status regeneration, compliance_input_state, event_context_index.
4. Classifiers list the three folders (change_type_paths, review_diff_threshold, section_file_list, project_root, gitignore_selfheal, worktree_isolation, churn_merge, gitattributes_union, pr_review_generated/skip_safety).
5. Reference guard (events_references.py + test) and removal of the 12 S3 replay-gate known-failing entries.
6. Integration test: real ensure_current on a behind-main branch with its own drop; status regeneration.
Tests first for each step; legacy tests unchanged; drops env replay for the S3 known entries.
