"""``build_verified_manifest`` — the PURE half of the keystone gate's
post-merge detective arm (ruling Q5; full design:
``.shipwright/planning/iterate/2026-09-10-keystone-detective-arm.md``, §4.1).

Split from ``_keystone_detective_core.py`` (code review, low — the combined
module crossed the 300-LOC guideline), the same pure/orchestration split
already used for this feature's own test modules
(``test_keystone_detective_core.py`` / ``test_keystone_detective_greenness.py``).
This half has no I/O: no git, no filesystem, no ``gh`` — only dict
transformation, so it is trivially testable and trivially safe to keep
separate from the orchestration half (``classify_commit``) that drives it.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from ci_execution_evidence import ExecutionEvidence  # noqa: E402

from ._keystone_base_manifest import ReadError  # noqa: E402  (re-exported: one import site for callers)

__all__ = ["build_verified_manifest"]


def build_verified_manifest(committed_manifest: dict, evidence: ExecutionEvidence) -> dict:
    """A copy of ``committed_manifest`` whose every AC-bound link's
    ``status``/``executed`` is overwritten from ``evidence.requirements`` —
    CI-VERIFIED values — instead of the committed file's own (untrusted, for a
    foreign commit) self-report. Pure: no git, no filesystem, no ``gh``.

    Matching is BY LINK ``id`` WITHIN THE SAME REQUIREMENT KEY, never
    globally — two requirements could share a test id in a hand-edited
    manifest, and this reader has no reason to assume otherwise (design §4.1).
    A link whose id is not found in the verified evidence's own list for that
    requirement is written as ``status: "enabled", executed: "not_run"`` —
    fail-closed (the same posture ``_layer_coverage_regen`` already takes for
    "broken evidence staging"), which reads as ``not_selected`` under
    ``evaluate_keystone``'s existing greenness walk rather than a silent pass.

    Raises :class:`ReadError` if the verified evidence itself carries two
    links with the SAME ``id`` within one requirement's aggregated
    ``tests[layer]`` lists — an ambiguous shape this reader refuses to
    silently resolve one way (external plan review, openai, medium).
    Deliberately scoped ACROSS layers, not per layer (external code review
    round 2, glm, disposed as correct-as-designed rather than fixed):
    substitution itself looks a link up BY ID ALONE, with no layer
    parameter, so a same-id collision in two different layers is exactly as
    ambiguous for substitution as one within a single layer — narrowing the
    check to per-layer would let substitution silently prefer whichever
    layer's dict happened to be visited last, reintroducing the very
    last-write-wins risk this check exists to close.

    A verified link whose own ``status``/``executed`` fields are missing or
    not strings is treated as ABSENT, not as authoritative ``None`` values
    (external code review round 2, glm, low) — the same fail-closed
    ``not_run`` fallback an unmatched id already gets, rather than writing a
    non-string sentinel into the manifest that ``evaluate_keystone`` was
    never contracted to handle.

    Returns a full, independent deep copy — no shared mutable state with
    ``committed_manifest`` ANYWHERE in the returned tree, not merely on the
    paths this function explicitly rebuilds (external code review round 2,
    both reviewers, medium — a top-level/sibling-key alias survived the
    first, narrower fix). A caller mutating the result cannot corrupt the
    manifest that was read from git.
    """
    verified_by_req: dict[str, dict[str, tuple[str, str]]] = {}
    for req_key, node in (evidence.requirements or {}).items():
        by_id: dict[str, tuple[str, str]] = {}
        for layer, links in (node.get("tests") or {}).items():
            if not isinstance(links, list):
                continue
            for link in links:
                if not isinstance(link, dict):
                    continue
                link_id = link.get("id")
                if not isinstance(link_id, str):
                    continue
                status, executed = link.get("status"), link.get("executed")
                if not isinstance(status, str) or not isinstance(executed, str):
                    # Malformed verified link -- treated as though this id
                    # were absent from the evidence entirely, so the
                    # substitution step below falls through to the same
                    # fail-closed `not_run` an unmatched id gets.
                    continue
                if link_id in by_id:
                    raise ReadError(
                        f"{req_key}: the verified execution evidence carries two links with "
                        f"id {link_id!r} in layer {layer!r} or across layers -- refusing to "
                        "guess which one is authoritative."
                    )
                by_id[link_id] = (status, executed)
        verified_by_req[req_key] = by_id

    result = copy.deepcopy(committed_manifest)
    requirements = result.get("requirements")
    if not isinstance(requirements, dict):
        return result
    for req_key, node in requirements.items():
        if not isinstance(node, dict):
            continue
        acs = node.get("acs")
        if not isinstance(acs, dict) or not acs:
            continue
        by_id = verified_by_req.get(req_key, {})
        for ac_node in acs.values():
            if not isinstance(ac_node, dict) or not isinstance(ac_node.get("tests"), dict):
                continue
            for links in ac_node["tests"].values():
                if not isinstance(links, list):
                    continue
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    link_id = link.get("id")
                    verified = by_id.get(link_id) if isinstance(link_id, str) else None
                    if verified is None:
                        link["status"] = "enabled"
                        link["executed"] = "not_run"
                    else:
                        link["status"], link["executed"] = verified
    return result
