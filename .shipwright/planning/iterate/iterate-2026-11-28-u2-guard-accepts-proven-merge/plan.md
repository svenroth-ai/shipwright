Goal: The release guard and the closing check accept a squash- or rebase-merged release when the record proves the merge commit carries exactly the checked release; the closing summary says the tag is pushed only when origin holds it.
Reason: A release on a squash-only repository could not be finished without hand work and lifting the guard (FINDINGS D110), and the closing summary kept saying the tag would be pushed later after it was pushed (D113(1)).
Reference: Campaign dfp-changelog-followups unit U2, brief .shipwright/planning/campaigns/2026-11-27-dfp-changelog-followups-BRIEF.md
Affected ACs: FR-01.09.AC11
AC item: {"confirmed": false, "decided_by": "code", "kind": "restore", "restores_ac": "FR-01.09.AC11"}
AC decisions: [{"ac": "FR-01.09.AC11", "mode": "auto", "answer": "auto", "kind": "restore", "answered_via": "none", "decided_by": "code", "confirmed": false}]
