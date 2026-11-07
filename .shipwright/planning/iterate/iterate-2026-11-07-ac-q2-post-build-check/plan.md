Goal: ac-at-start Q2 phase 1: after the build, the spec-reviewer checks each added or changed AC against the diff (matches or diverges); F11 warns only
Reason: Q1 records the promise before the build; nothing checks the finished code keeps it
Reference: .shipwright/planning/campaigns/2026-11-07-ac-at-start-Q2-PLAN.md
AC item: {"ac": "FR-01.11.AC50", "confirmed": false, "decided_by": "code", "files": ["shared/scripts/lib/ac_claims.py"], "kind": "add", "new_text": "Given a finished change added or changed a promise, when the reviewer checks it, then each such promise gets a verdict of matches or diverges against what was built, a divergence names the line that breaks it, and a divergence on a promise nobody confirmed is only a visible warning that never holds the change back.", "owner_fr": "FR-01.11"}
AC decisions: [{"ac": "FR-01.11.AC50", "mode": "auto", "answer": "auto", "kind": "add", "answered_via": "none", "decided_by": "code", "confirmed": false}]
