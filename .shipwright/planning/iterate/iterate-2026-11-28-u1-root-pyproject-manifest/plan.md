Goal: A release writes its version into the root pyproject.toml and the project's own package in uv.lock, through the existing manifest sync, with two new formats pyproject_toml and uv_lock.
Reason: FINDINGS D111: v0.37.0 bumped every plugin manifest but left the root pyproject.toml and uv.lock at the old version, because neither was a declarable manifest.
Reference: campaign dfp-changelog-followups unit U1 (brief 2026-11-27-dfp-changelog-followups-BRIEF.md section 1)
Affected ACs: FR-01.09.AC12
AC item: {"confirmed": false, "decided_by": "code", "kind": "restore", "restores_ac": "FR-01.09.AC12"}
AC decisions: [{"ac": "FR-01.09.AC12", "mode": "auto", "answer": "auto", "kind": "restore", "answered_via": "none", "decided_by": "code", "confirmed": false}]
