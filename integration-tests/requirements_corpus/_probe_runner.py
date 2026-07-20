"""Run one named false-verdict probe in an isolated subprocess.

    python _probe_runner.py --probe t1 --root <project> [--json <extra>]

The false-verdict checks live in two different import realms
(``shared/scripts/tools/verifiers`` and the compliance plugin), and importing
``group_i`` reorders ``sys.path`` and evicts ``sys.modules['tools']``. Driving
them from one pytest process would let one probe corrupt the next. Each probe
gets its own process; the test module reads back plain JSON and asserts on it
in prose.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_PARENT = str(Path(__file__).resolve().parent.parent)
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from requirements_corpus.collect import REPO_ROOT  # noqa: E402

PROBES: dict[str, str] = {
    "t1": "shared_tools", "t2": "shared_tools",
    "group_d_empty": "compliance", "group_i_empty": "compliance",
    "d_traceability_empty": "compliance", "d_traceability_populated": "compliance",
    "unsorted_seam": "adopt", "unsorted_seam_a2": "shared_tools",
}


def _paths(realm: str) -> None:
    from requirements_corpus.registry import REALMS
    for rel in REALMS[realm]["paths"]:
        p = str(REPO_ROOT / rel)
        if p not in sys.path:
            sys.path.insert(0, p)


def probe_t1(root: Path, _extra) -> dict:
    _paths("shared_tools")
    from verifiers.traceability_checks import check_t1_all_spec_frs_mapped
    return check_t1_all_spec_frs_mapped(root)


def probe_t2(root: Path, _extra) -> dict:
    _paths("shared_tools")
    from verifiers.traceability_checks import check_t2_no_orphan_rtm_rows
    return check_t2_no_orphan_rtm_rows(root)


def probe_group_d_empty(root: Path, _extra) -> dict:
    """The D-group guards, driven with an EMPTY requirement set.

    ``D2_with_refs`` added by S6: with zero spec FRs, an event that NAMES an FR is
    the maximally-red state -- the reference cannot possibly resolve. Without a
    case that carries such an event, D2's flip is invisible, because the empty
    event list produces "nothing to compare" either way.
    """
    _paths("compliance")
    from scripts.audit.group_d import _check_d1, _check_d2, _check_d4
    referencing = [{"type": "work_completed", "ts": "2026-01-01T00:00:00+00:00",
                    "affected_frs": ["FR-99.99"], "tests": {"total": 1, "passed": 1}}]
    return {
        "D1": list(_check_d1([], [], root)),
        "D2": list(_check_d2([], [], root)),
        "D4": list(_check_d4([], [])),
        "D2_with_refs": list(_check_d2([], referencing, root)),
    }


def probe_group_i_empty(root: Path, _extra) -> dict:
    _paths("compliance")
    from scripts.audit.group_i import run
    return [
        {"check_id": f.check_id, "status": f.status,
         "severity": f.severity, "detail": f.detail}
        for f in run(root, None, None)
    ]


def probe_d_traceability_empty(root: Path, _extra) -> dict:
    """The two sites that emit a POSITIVE claim over the empty set."""
    _paths("compliance")
    from scripts.audit._group_d_traceability import check_layer, check_orphan
    empty = {"schema_version": 3, "requirements": {}}
    return {"orphan": list(check_orphan(empty)),
            "layer": list(check_layer(empty))}


def probe_d_traceability_populated(root: Path, _extra) -> dict:
    """The same two sites over a manifest that DOES declare an active, covered FR.

    The compensating control for S6's empty-set guards: without it, replacing the
    positive claim with an unconditional skip would satisfy every FV-2 assertion
    while silencing the coverage plane outright.
    """
    _paths("compliance")
    from scripts.audit._group_d_traceability import check_layer, check_orphan
    populated = {"schema_version": 3, "requirements": {"01::FR-01.01": {
        "id": "FR-01.01", "status": "active", "priority": "Must",
        "required_layers": ["unit"], "required_layers_source": "explicit",
        "coverage": {"unit": "ok"}}}}
    return {"orphan": list(check_orphan(populated)),
            "layer": list(check_layer(populated))}


def probe_unsorted_seam(root: Path, extra) -> dict:
    """Prove the walk preserves whatever order enumeration hands it.

    Sorting the real result would HIDE the behaviour being frozen, so instead
    the enumeration seam is controlled: rglob is replaced with one that yields a
    deliberately non-lexical order, and we record which spec the walk acted on.
    Running it twice with opposite orders shows the pick tracks the seam.
    """
    _paths("adopt")
    import importlib.util
    path = REPO_ROOT / "plugins/shipwright-adopt/scripts/checks/validate_adoption.py"
    spec = importlib.util.spec_from_file_location("_swp_validate_adoption", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_swp_validate_adoption"] = mod
    spec.loader.exec_module(mod)

    real_rglob = Path.rglob
    out = {}
    for label, reverse in (("forward", False), ("reverse", True)):
        def fake(self, pattern, _rev=reverse):
            found = sorted(real_rglob(self, pattern))
            return iter(list(reversed(found)) if _rev else found)
        Path.rglob = fake
        try:
            errors = mod._validate_spec(root)
        finally:
            Path.rglob = real_rglob
        out[label] = [e.replace(str(root), "<root>").replace("\\", "/")
                      for e in errors]
    return out


def probe_unsorted_seam_a2(root: Path, extra) -> dict:
    """The same seam probe for ``adopt_compliance.check_a2_spec_has_frs``.

    It is the OTHER ``order_sensitive`` target: its picked path is masked out of
    the matrix, so without this probe an S2 change adding ``sorted()`` to its
    rglob would move no golden cell and no test would look -- a walk would stop
    being order-dependent and the harness would certify "no behaviour change".
    (Caught in adversarial review: the mask had exactly one compensating
    control, covering only one of the two masked targets.)
    """
    _paths("shared_tools")
    from verifiers.adopt_compliance import check_a2_spec_has_frs

    real_rglob = Path.rglob
    out = {}
    for label, reverse in (("forward", False), ("reverse", True)):
        def fake(self, pattern, _rev=reverse):
            found = sorted(real_rglob(self, pattern))
            return iter(list(reversed(found)) if _rev else found)
        Path.rglob = fake
        try:
            finding = check_a2_spec_has_frs(root)
        finally:
            Path.rglob = real_rglob
        out[label] = {k: str(v).replace(str(root), "<root>").replace("\\", "/")
                      for k, v in finding.items()}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True, choices=sorted(PROBES))
    ap.add_argument("--root", required=True)
    ap.add_argument("--json", default="null")
    args = ap.parse_args()
    fn = globals()[f"probe_{args.probe}"]
    result = fn(Path(args.root), json.loads(args.json))
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
