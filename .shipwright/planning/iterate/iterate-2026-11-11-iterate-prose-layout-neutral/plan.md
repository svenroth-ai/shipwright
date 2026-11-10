Goal: Make iterate prose and the verifier hint layout-neutral
Reason: The per-run event layout is live in this repo
Reference: events layout follow-ups
Affected ACs: FR-01.11
AC item: {"confirmed": false, "decided_by": "code", "files": ["shared/scripts/tools/verifiers/iterate_checks.py"], "kind": "add", "new_text": "Given a run's event is only in the working copy and not yet committed, when the finalization check fails, then its message names how to stage the event for both the single-file and the per-run layout.", "owner_fr": "FR-01.11"}
AC decisions: [{"ac": "FR-01.11.new", "mode": "auto", "answer": "auto", "kind": "add", "answered_via": "none", "decided_by": "code", "confirmed": false}]
