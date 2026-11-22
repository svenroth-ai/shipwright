Goal: Catalogue the changelog golden freeze test in the infra test catalog
Reason: Step 1 of 2 before the stop-2 lock: the test-tag gate honours covers_none only for files named in the catalog at the merge-base, so the catalog entry must merge before the retag
Reference: dfp-pilot-changelog-p1-p2p stop 2
AC item: {"ac": "FR-01.11.AC55", "confirmed": false, "decided_by": "code", "files": ["shared/config/infra_test_paths.json"], "kind": "unchanged"}
AC decisions: [{"ac": "FR-01.11.AC55", "mode": "auto", "answer": "auto", "kind": "unchanged", "answered_via": "none", "decided_by": "code", "confirmed": false}]
