"""THE KEYSTONE GATE's manifest-link readers, split out of ``_keystone_core``
to buy back headroom at its 300-line limit after the Stage-3 doubt-review fix
(partial-binding-reduction detection). Pure manifest reads, no git.

Re-exported from :mod:`_keystone_core`, which stays the one import site
callers and tests use.
"""

from __future__ import annotations

from ._keystone_finding import FAILED, NOT_SELECTED, SKIPPED, Finding


class EmptyLinkWalk(RuntimeError):
    """The greenness walk was entered with zero links — a programming error,
    never a pass. Every caller is gated on ``head_links >= 1``, so reaching this
    is a bug in the gate, not a finding about the repo."""


def links_for(manifest: dict, fr_id: str, ac_id: str) -> list[dict]:
    """Every link bound to ``(fr_id, ac_id)``, flattened across layers.

    ``[]`` when ANY level is absent (no requirement with that display id, no
    ``acs`` node — e.g. a v3-era manifest — no such AC, or an empty ``tests``
    map). The count, never the node's presence, is what every caller keys on.
    Looks the FR up by its DISPLAY id (``node["id"]``), not the manifest's
    namespaced top-level key: the change set comes from spec.md, which knows only
    display ids.

    **ACTIVE nodes only** — no reviewer asked for this, found during build (NOT
    the same as the separate glm-low finding at §7 about retiring an FR while
    editing its criterion). This used to pool every node carrying the id,
    including RETIRED ones, while ``_keystone_layer_gap`` restricted itself to
    ``_active_nodes`` — an asymmetry that was fail-OPEN, not fail-closed as its
    docstring claimed: a retired duplicate silently ADDS to the head count,
    turning a `base >= 1, head 0` ``binding_removed`` into an ordinary greenness
    walk. Two active nodes sharing a display id still pool (a real collision,
    fail-closed there); ``_keystone_layer_gap`` routes that ADVISORY like its
    siblings.
    """
    out: list[dict] = []
    for node in (manifest.get("requirements") or {}).values():
        if not isinstance(node, dict) or node.get("id") != fr_id:
            continue
        if node.get("status") != "active":
            continue
        ac_node = (node.get("acs") or {}).get(ac_id)
        if not isinstance(ac_node, dict):
            continue
        for links in (ac_node.get("tests") or {}).values():
            if isinstance(links, list):
                out.extend(x for x in links if isinstance(x, dict))
    return out


def walk_links(links: list[dict], fr_id: str, ac_id: str) -> list[Finding]:
    """One HARD finding per link that is not executed-passing. ``[]`` = all green.

    Raises :class:`EmptyLinkWalk` on empty ``links``. The three non-green
    outcomes stay DISTINCT because a bare "not green" cannot tell an operator
    what to do: a failing test, a skipped one, and one this run never executed
    have three different remedies.
    """
    if not links:
        raise EmptyLinkWalk(
            f"{fr_id}/{ac_id}: the greenness walk was entered with zero links -- "
            "all() over an empty set is vacuously True, which would report a "
            "vanished binding as green. Callers must gate on head_links >= 1."
        )
    findings: list[Finding] = []
    for link in links:
        test_id = str(link.get("id") or "<unknown test>")
        status = link.get("status")
        executed = link.get("executed")
        if status == "enabled" and executed == "pass":
            continue
        # STATUS FIRST -- no reviewer asked for this, found during build (same
        # honesty rule as deviation 3). A link that is `disabled` AND
        # `executed: fail` used to report `failed` ("fix the code"), but a
        # disabled test's `executed` is stale by construction; the actionable
        # fact is that it is disabled. Operator-facing, so pinned by a test.
        if status != "enabled":
            findings.append(Finding(
                SKIPPED, fr_id, ac_id,
                f"{test_id} is {status!r}, not 'enabled' -- a green-but-skipped test does not "
                "satisfy the gate.",
                "hard",
            ))
        elif executed == "fail":
            findings.append(Finding(
                FAILED, fr_id, ac_id,
                f"{test_id} FAILED in this run. Fix the code, or update the test as the "
                "TDD expression of the new acceptance criterion -- never weaken its assertion.",
                "hard",
            ))
        else:
            findings.append(Finding(
                NOT_SELECTED, fr_id, ac_id,
                f"{test_id} was not executed by this run (executed={executed!r}). This AC's "
                "binding names a test CI did not run: retag it to a test CI runs, or fix "
                "evidence staging.",
                "hard",
            ))
    return findings


__all__ = ["EmptyLinkWalk", "links_for", "walk_links"]
