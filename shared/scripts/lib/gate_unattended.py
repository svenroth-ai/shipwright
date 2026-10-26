"""Unattended-answer rules for the phase-gate catalog (Campaign B5, brief D5).

``autonomy: unattended`` is opt-in per gate. An ``orchestrator-approve`` gate that is
not constitution-locked auto-approves ONLY if the catalog carries a reviewed
``unattended_answer`` for it; every other gate escalates. This module owns the rule
(the denylist, the validator check, the resolver lookup) so ``gate_policy`` stays the
policy mechanism. The resolver never answers a gate itself: the phase-runner still
returns gate-pending and the master/CLI applies ``unattended_answer`` after its own
hash and FR-coverage checks.
"""
from __future__ import annotations

from typing import Any, Optional

UNATTENDED = "unattended"

# Gates that must never carry an ``unattended_answer`` (explicit ids, pinned by a
# test), plus two id families matched by suffix. Constitution-locked and hard-stop
# gates are rejected separately by the validator.
UNATTENDED_DENYLIST = frozenset({
    "build.migration-preflight-fail",
    "build.migration-apply-fail",
    "build.env-validation-missing-vars",
    "deploy.missing-env-vars",
    "deploy.post-migration-manual-steps",
    "project.supabase-project-ref",
    "build.browser-verify-prereq-unresolved",
    "build.browser-verify-fix-exhausted",
    "plan.validate-input",
    "build.section-file-required",
    "project.session-conflict",
})
_DENIED_SUFFIXES = ("out-of-sequence-continue", "prereqs-missing")


def is_denylisted(gate_id: str) -> bool:
    return gate_id in UNATTENDED_DENYLIST or gate_id.endswith(_DENIED_SUFFIXES)


def validate_unattended(where: str, gate: dict[str, Any]) -> list[str]:
    """Errors for one gate's ``unattended_answer`` (none when the key is absent)."""
    if "unattended_answer" not in gate:
        return []
    answer = gate["unattended_answer"]
    errors: list[str] = []
    if not isinstance(answer, str) or not answer.strip():
        errors.append(f"{where}: unattended_answer must be a non-empty str")
    if gate.get("policy") != "orchestrator-approve":
        errors.append(f"{where}: only orchestrator-approve gates may carry an unattended_answer")
    if gate.get("constitution") is True:
        errors.append(f"{where}: constitution-locked gate must not carry an unattended_answer")
    gid = gate.get("id")
    if isinstance(gid, str) and is_denylisted(gid):
        errors.append(f"{where}: denylisted gate must not carry an unattended_answer")
    return errors


def unattended_answer_for(gate: dict[str, Any], autonomy: Optional[str]) -> Optional[str]:
    """The reviewed answer, only under ``unattended`` and only for an eligible gate
    (fail closed: a locked / hard-stop / denylisted gate never yields one even if an
    unvalidated catalog dict carries it)."""
    if autonomy != UNATTENDED or validate_unattended(gate.get("id", "?"), gate):
        return None
    return gate.get("unattended_answer")
