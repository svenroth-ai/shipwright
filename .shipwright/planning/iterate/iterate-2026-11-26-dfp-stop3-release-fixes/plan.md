Goal: Fix the stop-3 release defects: tag-only pushes after a merge are judged by the tag (D109); the Step 6 release commit names only known paths, carries the consumed drop deletions and the events sync wrote, and stops before staging when the tree holds unrelated changes (D21, D22, D23, D25).
Reason: The stop-3 live runs of the converted changelog plugin could not finish a release: the guard blocked the tag push after the PR merge, and Step 6 failed or left the tree dirty for the release audit.
Reference: .shipwright/planning/campaigns/2026-10-25-dfp-pilot-changelog-FINDINGS.md (D21, D22, D23, D25, D109)
Affected ACs: FR-01.09.AC01
