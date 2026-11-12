Goal: Read git and gh output as UTF-8 bytes in pr_review_local and check_required_checks; say in two verifier texts that a late record cannot be cleared in this run.
Reason: On Windows text=True garbled non-ASCII check names (flagged twice) and turned a lone CR into LF in the preflight diff.
Reference: campaign leadwright-followups U4; cards trg-cce2ed3b, trg-87a3da4a, trg-4c33d714
AC item: {"confirmed": false, "decided_by": "code", "kind": "restore", "restores_ac": "FR-01.17.AC06"}
AC decisions: [{"ac": "FR-01.17.AC06", "mode": "auto", "answer": "auto", "kind": "restore", "answered_via": "none", "decided_by": "code", "confirmed": false}]
