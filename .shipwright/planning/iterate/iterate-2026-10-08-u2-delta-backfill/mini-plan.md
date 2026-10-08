# Mini-plan U2 delta backfill
1. Measure untagged tests added since 2026-09-16 per root (collector on base vs HEAD archive).
2. Run backfill_test_links --dry-run and backfill_ac_provenance (dry then --write) over the delta.
3. Write only deterministic high-confidence tags: both engines yield zero, so no test file is edited.
4. Commit the measurement doc, file ONE triage card (trg-067e08fa) for the 1,440 unmapped tests; nothing deleted.
5. Confirm collector on HEAD gives invalid_tags 0.
Finalize (F-chain) with decision drop, changelog drop, iterate entry.
