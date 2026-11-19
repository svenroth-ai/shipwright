Goal: Seed the infrastructure-test catalog, show the real error of a failed compliance refresh, document the WSL2 Linux test run
Reason: #1082 needs the catalog at a merge-base before harness tests can be reclassified; a cold-start failure hid its cause behind uv warnings (trg-2dfb47bf)
Reference: trg-2dfb47bf / #1082
Affected ACs: FR-01.11.AC56
AC item: {"ac": "FR-01.11.AC56", "confirmed": false, "decided_by": "code", "files": ["shared/config/infra_test_paths.json", "shared/scripts/lib/failure_text.py", "shared/scripts/tools/finalize_iterate.py"], "kind": "add", "new_text": "Given the compliance refresh of a finishing run fails before it reports anything (for example a first run that still has to build the compliance plugin environment), when the failure is logged, then the log shows the real error lines from the failed process instead of only the advisory warnings printed before it, and still shows the generator errors the refresh reported as data.", "owner_fr": "FR-01.11"}
AC decisions: [{"ac": "FR-01.11.AC56", "mode": "auto", "answer": "auto", "kind": "add", "answered_via": "none", "decided_by": "code", "confirmed": false}]
