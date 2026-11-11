Goal: The finalization verifier and the release-notes tools declare their own packages so a plain uv run works from any folder
Reason: Under a plain uv run outside the monorepo root the condenser answered 'openai package not installed' and the verifier's schema checks degraded silently
Reference: campaign events-followups U2
Catalog gap: FR-01.11
AC item: {"confirmed": false, "decided_by": "code", "files": ["shared/scripts/tools/condense_release_notes.py", "shared/scripts/tools/verify_iterate_finalization.py"], "kind": "add", "new_text": "Given a fresh checkout with no extra packages installed by hand, when the finalization verifier or the release-notes condenser is started with a plain uv run from any folder, then it starts and does its work instead of stopping on a missing package.", "owner_fr": "FR-01.11"}
AC decisions: [{"ac": "FR-01.11.new", "mode": "auto", "answer": "auto", "kind": "add", "answered_via": "none", "decided_by": "code", "confirmed": false}]
