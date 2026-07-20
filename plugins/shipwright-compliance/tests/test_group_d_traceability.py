"""D-orphan + D-layer detective tests (traceability campaign TT2, Spec §5).

RED before TT2 (``_group_d_traceability`` did not exist); green after. This file holds the
UNIT-level checks (``check_orphan`` / ``check_layer`` over hand-built manifest dicts): the
provenance release valve (explicit FAIL vs legacy advisory), the fan-out fail-closed rule,
``invalid_layers``, and the wiring. The real-``build_manifest`` fan-out / collision +
coordinator-hardening tests (MUST-FIX 1–3, SHOULD-FIX 4/6) live in
``test_group_d_hardening.py`` (keeps this file under the 300-LOC guideline).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from scripts.audit import _group_d_traceability as gdt  # noqa: E402


# ---------------------------------------------------------------------------
# Manifest builders (unit level)
# ---------------------------------------------------------------------------


def _node(fr_id, *, status="active", priority="Must", source="explicit",
          required=("unit",), coverage=None, tests=None):
    return {
        "id": fr_id, "spec_path": "s/spec.md", "title": fr_id, "priority": priority,
        "status": status, "required_layers": list(required),
        "required_layers_source": source, "tests": tests or {},
        "coverage": coverage or {},
    }


def _manifest(reqs, *, orphans=None, invalid_layers=None):
    """Assemble a v3 manifest from ``(spec-namespace, node)`` pairs.

    The KEY derives from the node's own FR id (v3), not from the namespace. Two entries
    sharing an id therefore collide on one key — which the real collector refuses to
    produce at all (it fails closed). A fixture that still wants two such nodes is
    exercising the HAND-EDITED manifest path, which the node-count collision guard is
    what remains to cover; the namespace disambiguates those keys so both nodes survive
    into the dict, exactly as a corrupt-but-parseable artifact on disk would.
    """
    keyed: dict = {}
    for ns, node in reqs:
        key = f"{node['id'][3:5]}::{node['id']}"
        keyed[key if key not in keyed else f"{ns}::{node['id']}"] = node
    return {
        "schema_version": 3, "collector_version": "test", "generated_at": "t",
        "source_commit": "x", "spec_hash": "h", "requirements": keyed,
        "orphans": orphans or [], "invalid_tags": [],
        "invalid_layers": invalid_layers or [], "untagged_tests": [],
    }


# ---------------------------------------------------------------------------
# D-orphan
# ---------------------------------------------------------------------------


def test_orphan_passes_when_no_orphans():
    status, sev, detail, ev, cmd = gdt.check_orphan(_manifest([]))
    assert status == "pass"
    assert cmd is None


def test_orphan_flags_confirmed_orphan_medium():
    m = _manifest([], orphans=[
        {"test": "e2e/old.spec.ts::copy", "tagged_fr": "FR-09.09",
         "reason": "fr_removed", "category": "confirmed_orphan"},
    ])
    status, sev, detail, ev, cmd = gdt.check_orphan(m)
    assert status == "fail"
    assert sev == "MEDIUM"
    assert "FR-09.09" in detail
    assert any("e2e/old.spec.ts::copy" in e for e in ev)  # test path is in EVIDENCE
    # The copy-paste command carries only the schema-pinned FR (never the untrusted test
    # path) — a test id with a shell metachar can't break it (external-review MED).
    assert "FR-09.09" in cmd and "e2e/old.spec.ts::copy" not in cmd


def test_orphan_unmapped_alone_is_informational_not_accusation():
    """R4: an unmapped test must not become a stale-feature accusation."""
    m = _manifest([], orphans=[
        {"test": "tests/test_x.py::t", "tagged_fr": None,
         "reason": "fr_absent", "category": "unmapped"},
    ])
    status, sev, detail, ev, cmd = gdt.check_orphan(m)
    assert status == "pass"
    assert "unmapped" in detail


# ---------------------------------------------------------------------------
# D-layer — provenance release valve (carry-forward #2)
# ---------------------------------------------------------------------------


def test_layer_explicit_missing_layer_fails_by_priority():
    m = _manifest([
        ("01-a", _node("FR-01.01", priority="Must", source="explicit",
                       required=("unit", "e2e"),
                       coverage={"unit": "ok", "e2e": "MISSING"})),
    ])
    status, sev, detail, ev, cmd = gdt.check_layer(m)
    assert status == "fail"
    assert sev == "HIGH"  # Must
    assert any("e2e" in e for e in ev)


def test_layer_should_priority_is_medium():
    m = _manifest([
        ("01-a", _node("FR-01.02", priority="Should", source="explicit",
                       required=("e2e",), coverage={"e2e": "MISSING"})),
    ])
    status, sev, *_ = gdt.check_layer(m)
    assert status == "fail"
    assert sev == "MEDIUM"


def test_layer_legacy_missing_layer_is_advisory_not_fail():
    """Carry-forward #2: a legacy-provenance FR missing a layer WARNs (surfaced),
    never FAILs — else the all-MISSING pre-TT8 monorepo drowns in HIGH findings."""
    m = _manifest([
        ("01-a", _node("FR-01.03", priority="Must", source="defaulted_legacy",
                       required=("unit",), coverage={"unit": "MISSING"})),
    ])
    status, sev, detail, ev, cmd = gdt.check_layer(m)
    assert status == "pass"          # advisory — NOT any_fail
    assert "advisory" in detail
    assert ev and "advisory" in ev[0]  # still surfaced


def test_layer_ok_coverage_is_no_gap():
    m = _manifest([
        ("01-a", _node("FR-01.04", source="explicit", required=("unit",),
                       coverage={"unit": "ok"})),
    ])
    status, *_ = gdt.check_layer(m)
    assert status == "pass"


def test_layer_removed_fr_is_not_evaluated():
    m = _manifest([
        ("01-a", _node("FR-01.05", status="removed", source="explicit",
                       required=("unit", "e2e"), coverage={"unit": "n/a", "e2e": "n/a"})),
    ])
    status, *_ = gdt.check_layer(m)
    assert status == "pass"  # removed FRs carry no live coverage obligation


# ---------------------------------------------------------------------------
# D-layer — namespace fan-out fail-closed (carry-forward #1)
# ---------------------------------------------------------------------------


def test_layer_fanout_collision_ok_is_not_credited_but_advisory():
    """A display id shared by ≥2 namespaces can be false-satisfied by ONE fanned tag.
    Fail-closed vs false-GREEN: the ``ok`` is NOT credited (surfaced as an
    ``ambiguous_fanout`` gap). Fail-closed vs false-RED: it is ADVISORY (not a HARD
    ``any_fail``), because a collision explicit FR is structurally unsatisfiable under
    un-namespaced tags — that remedy is deferred to TT5 (MUST-FIX 2)."""
    m = _manifest([
        ("01-a", _node("FR-03.01", source="explicit", required=("unit",),
                       coverage={"unit": "ok"})),
        ("02-b", _node("FR-03.01", source="explicit", required=("unit",),
                       coverage={"unit": "ok"})),
    ])
    status, sev, detail, ev, cmd = gdt.check_layer(m)
    assert status == "pass"                                 # advisory, not a HARD fail
    assert any("ambiguous_fanout" in e for e in ev)         # but NOT silently credited
    assert "deferred to TT5" in detail


def test_layer_non_collision_ok_is_credited():
    """The complement: a UNIQUE display id with ok coverage is credited (no false-red)."""
    m = _manifest([
        ("01-a", _node("FR-03.01", source="explicit", required=("unit",),
                       coverage={"unit": "ok"})),
        ("02-b", _node("FR-04.01", source="explicit", required=("unit",),
                       coverage={"unit": "ok"})),
    ])
    status, *_ = gdt.check_layer(m)
    assert status == "pass"


# ---------------------------------------------------------------------------
# D-layer — invalid_layers hygiene (carry-forward #3)
# ---------------------------------------------------------------------------


def test_layer_invalid_layers_is_hard_finding():
    m = _manifest(
        [("01-a", _node("FR-05.01", source="explicit", required=("unit",),
                        coverage={"unit": "ok"}))],
        invalid_layers=[{"fr": "FR-05.02", "spec_path": "s", "raw": "int, db",
                         "reason": "no_canonical_layer"}],
    )
    status, sev, detail, ev, cmd = gdt.check_layer(m)
    assert status == "fail"
    assert any("FR-05.02" in e and "int, db" in e for e in ev)


# ---------------------------------------------------------------------------
# Wiring + fail-closed manifest loading
# ---------------------------------------------------------------------------


def test_traceability_findings_skip_when_manifest_absent(tmp_path):
    findings = gdt.traceability_findings(tmp_path)
    ids = {f.check_id: f for f in findings}
    assert ids["D-orphan"].status == "skip"
    assert ids["D-layer"].status == "skip"


def test_load_manifest_rejects_non_v2(tmp_path):
    p = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"schema_version": 1, "requirements": {}}', encoding="utf-8")
    assert gdt.load_manifest(tmp_path) is None  # fail-closed: not v2 → skip, not pass


def test_group_d_run_emits_traceability_findings_end_to_end(tmp_path):
    """End-to-end through ``group_d.run`` with a committed valid manifest — guards the
    ``out.extend(traceability_findings(...))`` wiring (a broken splice would leave the
    helper-level tests green but drop the findings)."""
    from scripts.audit import group_d  # noqa: PLC0415
    m = _manifest(
        [("01-a", _node("FR-01.01", source="explicit", required=("e2e",),
                        coverage={"e2e": "MISSING"}))],
        orphans=[{"test": "e2e/dead.spec.ts::t", "tagged_fr": "FR-09.09",
                  "reason": "fr_removed", "category": "confirmed_orphan"}],
    )
    p = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m), encoding="utf-8")
    by_id = {f.check_id: f for f in group_d.run(tmp_path, {}, None)}
    assert by_id["D-orphan"].status == "fail"       # confirmed orphan surfaced
    assert by_id["D-layer"].status == "fail"        # explicit FR missing e2e
    for f in by_id.values():
        assert f.source == "detective-only"


# Real-``build_manifest`` fan-out / collision + hardening tests live in
# ``test_group_d_hardening.py`` (keeps this unit-level file under the 300-LOC guideline).
