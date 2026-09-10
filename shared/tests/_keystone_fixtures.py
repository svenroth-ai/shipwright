"""Fixture builders shared by the P3.6 keystone-evaluator test modules.

Not a ``test_*`` file, so pytest does not collect it — the same shape
``_pr_review_workflows.py`` and ``_reconcile_helpers.py`` already use in this
directory. It exists because ``test_keystone_core.py`` (link vocabulary) and
``test_keystone_core_arms.py`` (layer gap + the AC-1 arms) need the identical
manifest shapes, and duplicating a manifest builder across two test modules is
how the two halves drift into testing different fixtures.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


@dataclass
class StubChangeSet:
    """Duck-typed stand-in for ``_keystone_ac_digest.AcChangeSet``.

    The evaluator reads the change set by attribute only, which is what keeps it
    testable without a repo, a git history or a spec file.
    """

    changed: set = field(default_factory=set)
    added: set = field(default_factory=set)
    removed: set = field(default_factory=set)
    unminted_changed: list = field(default_factory=list)
    new_frs_without_criteria: list = field(default_factory=list)
    reader_divergence: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def link(test_id="shared/tests/test_x.py::test_y", *, layer="unit",
         status="enabled", executed="pass"):
    return {"id": test_id, "layer": layer, "status": status, "executed": executed}


def manifest(fr_id="FR-01.01", ac_id="AC01", links_by_layer=None, *,
             required_layers=("unit",), source="inferred_legacy",
             acs_node="default", status="active"):
    """A v4-shaped manifest carrying one requirement.

    ``acs_node=None`` omits the ``acs`` map entirely (a v3-era manifest);
    ``acs_node={}`` gives the requirement an ``acs`` map with no such AC; and
    ``acs_node={"AC01": {"tests": {}}}`` gives the AC a node whose ``tests`` map
    is EMPTY — the input on which the node vocabulary and the link vocabulary
    disagree (design §5.3).

    The top-level key is deliberately NAMESPACED (``ns::FR-01.01``) while
    ``node["id"]`` carries the display id: the evaluator must look requirements
    up by display id, since the change set is computed from spec.md, which knows
    nothing about namespaces.
    """
    node = {
        "id": fr_id, "status": status,
        "required_layers": list(required_layers),
        "required_layers_source": source,
    }
    if acs_node == "default":
        node["acs"] = {ac_id: {"tests": dict(links_by_layer or {})}}
    elif acs_node is not None:
        node["acs"] = acs_node
    return {"requirements": {f"ns::{fr_id}": node}}


def bound(fr_id, ac_id, links, **kw):
    """``manifest`` with ``links`` bound at the ``unit`` layer."""
    return manifest(fr_id, ac_id, {"unit": links}, **kw)
