Goal: A PreToolUse hook that denies an outward release action while a release is in progress and its record for HEAD is missing.
Reason: Models ran git push --tags, git push origin HEAD and gh pr merge by hand before the verified release record existed (second pass B2).
Reference: campaign dfp-pilot-changelog-p3-p8 unit P4b; SECOND-PASS B2
Affected ACs: FR-01.09.AC01
AC item: {"ac": "FR-01.09.AC01", "confirmed": false, "decided_by": "code", "files": ["plugins/shipwright-changelog/hooks/hooks.json", "plugins/shipwright-changelog/scripts/hooks/release_guard.py", "plugins/shipwright-changelog/scripts/hooks/release_guard_commands.py"], "kind": "unchanged"}
AC decisions: [{"ac": "FR-01.09.AC01", "mode": "auto", "answer": "auto", "kind": "unchanged", "answered_via": "none", "decided_by": "code", "confirmed": false}]
