Goal: release.py push-tag proves a squash or rebase merge commit (PR head is the release, merge commit on the freshly fetched base, merge proof holds), writes the proof into the release record and moves the local tag onto it while origin does not hold the tag; foreign commits merged into the base stop it with foreign_commits_on_base and nothing is written.
Reason: On a squash-only repository the release commit never reaches the base, so push-tag waited forever and the release could not be finished without hand work (FINDINGS D110 part 2); foreign commits squashed into the release would have shipped without their changelog entries (D112).
Reference: Campaign dfp-changelog-followups unit U3, brief .shipwright/planning/campaigns/2026-11-27-dfp-changelog-followups-BRIEF.md
Affected ACs: FR-01.09.AC11
AC item: {"confirmed": false, "decided_by": "code", "kind": "restore", "restores_ac": "FR-01.09.AC11"}
AC decisions: [{"ac": "FR-01.09.AC11", "mode": "auto", "answer": "auto", "kind": "restore", "answered_via": "none", "decided_by": "code", "confirmed": false}]
