Goal: The AC record's order check reads a branch with several commits correctly
Reason: An empty line in the git log output counted as a code file, so a record committed after a docs-only commit was flagged as late
Reference: MEASURE 7.1, deterministic-first programme brief rev 5
AC item: {"confirmed": false, "decided_by": "code", "files": ["shared/scripts/lib/ac_record.py"], "kind": "restore", "restores_ac": "FR-01.11.AC49"}
AC decisions: [{"ac": "FR-01.11.AC49", "mode": "auto", "answer": "auto", "kind": "restore", "answered_via": "none", "decided_by": "code", "confirmed": false}]
