# Mini-plan S0 (events-drop-files)
Goal: land a dormant drops path (events_layout.py: layout switch, rotate-on-commit write path, assembled read), wire it into record_event append paths and lib.config.read_events_result, add bare-origin harness test (legacy 3/3 conflict vs drops 3/3 clean under merge-tree without union), unsplit/split fixture pair + content-only splitter, and the replay gate (tool + ratcheted known-failing JSON split by unit + CI step with budget).
Files: shared/scripts/lib/events_layout.py (new), lib/config.py, tools/record_event.py (net 0 lines), tools/events_replay_gate.py (+ known JSON), shared/tests/test_events_layout.py, _events_split.py, fixtures, integration-tests/test_events_drops_harness.py, ci.yml step, docs/hooks-and-pipeline.md.
Tests: unit (switch precedence, plain-env no-op, rotation, assembled read == unsplit order), harness (3 tests), gate run once for baseline.
Risks: ADR-045 import contexts (events_layout only imported via lib package from config/record_event); bloat (record_event exception file kept at 728 lines); Windows-measured budget.
Alternative approach considered: none beyond the brief.

Plan-review amendments adopted: precedence matrix test; legacy bytes == pre-change test; rotation/concurrency sequence documented in events_layout docstring + concurrent exactly-once test; harness asserts merged contents; CI gate step uses --strict-stale. Declined: migration-only gate (BRIEF section 3 S0 mandates the standing ratchet).
