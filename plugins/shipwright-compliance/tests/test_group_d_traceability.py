"""D-orphan + D-layer detective tests (traceability campaign TT2, Spec §5).

RED before TT2 (``_group_d_traceability`` did not exist); green after. Two layers:

* **unit** — ``check_orphan`` / ``check_layer`` over hand-built manifest dicts. Pins the
  provenance release valve (explicit FAIL vs legacy advisory), the namespace fan-out
  fail-closed rule for D-layer, ``invalid_layers``, and the R1 executed-passing coverage.
* **integration** — ``build_manifest`` over synthetic multi-namespace fixtures, so the
  frozen-grammar fan-out is exercised end-to-end: a tag resolving to a live FR in ANY
  namespace is never an orphan; a tag resolving only to a removed FR is.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from scripts.audit import _group_d_traceability as gdt  # noqa: E402
from scripts.lib.collectors.test_links import build_manifest  # noqa: E402


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
    keyed = {}
    for ns, node in reqs:
        keyed[f"{ns}::{node['id']}"] = node
    return {
        "schema_version": 2, "collector_version": "test", "generated_at": "t",
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


def test_layer_fanout_collision_ok_is_not_credited():
    """A display id shared by ≥2 active namespaces can be false-satisfied by ONE
    fanned tag. Fail-closed: the ``ok`` is NOT credited → the explicit FR still
    fails, reason ambiguous_fanout."""
    m = _manifest([
        ("01-a", _node("FR-03.01", source="explicit", required=("unit",),
                       coverage={"unit": "ok"})),
        ("02-b", _node("FR-03.01", source="explicit", required=("unit",),
                       coverage={"unit": "ok"})),
    ])
    status, sev, detail, ev, cmd = gdt.check_layer(m)
    assert status == "fail"
    assert any("ambiguous_fanout" in e for e in ev)


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


# ---------------------------------------------------------------------------
# Integration — frozen-grammar fan-out through build_manifest (carry-forward #1)
# ---------------------------------------------------------------------------


def _spec(fr_rows: str, removed_rows: str = "") -> str:
    body = "# Spec\n\n| FR | Description | Priority | Layers |\n| --- | --- | --- | --- |\n" + fr_rows
    if removed_rows:
        body += "\n## Removed Requirements\n\n| FR | Description | Priority |\n| --- | --- | --- |\n" + removed_rows
    return body + "\n"


def _build(tmp_path):
    ns_a = tmp_path / ".shipwright" / "planning" / "01-a"
    ns_b = tmp_path / ".shipwright" / "planning" / "02-b"
    ns_a.mkdir(parents=True)
    ns_b.mkdir(parents=True)
    # 01-a: FR-03.01 ACTIVE. 02-b: FR-03.01 REMOVED + FR-09.09 REMOVED.
    (ns_a / "spec.md").write_text(
        _spec("| FR-03.01 | Live requirement | Must | unit |\n"), encoding="utf-8")
    (ns_b / "spec.md").write_text(
        _spec("| FR-08.01 | Other live | Must | unit |\n",
              "| FR-03.01 | Old dup | Must |\n| FR-09.09 | Retired feature | Must |\n"),
        encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    # One test fans to FR-03.01 (live in 01-a, removed in 02-b) → NOT an orphan.
    (tests_dir / "test_live.py").write_text(
        'import pytest\n\n@pytest.mark.covers("FR-03.01")\ndef test_live():\n    assert True\n',
        encoding="utf-8")
    # One test points ONLY at a removed FR → confirmed orphan.
    (tests_dir / "test_dead.py").write_text(
        'import pytest\n\n@pytest.mark.covers("FR-09.09")\ndef test_dead():\n    assert True\n',
        encoding="utf-8")
    return build_manifest(
        tmp_path,
        spec_files=[ns_a / "spec.md", ns_b / "spec.md"],
        test_roots=[tests_dir],
        evidence={},
    )


def test_orphan_fanout_live_in_any_namespace_is_not_flagged(tmp_path):
    """Direction 1 — a tag resolving to a live FR in ANY namespace (even while a
    same-id FR is Removed in another split) is coverage, never an orphan."""
    manifest = _build(tmp_path)
    orphan_frs = {o["tagged_fr"] for o in manifest["orphans"]}
    assert "FR-03.01" not in orphan_frs               # resolved live in 01-a
    status, *_ = gdt.check_orphan(manifest)
    # FR-09.09 IS a real orphan, so the check fails — but NOT because of FR-03.01.
    assert status == "fail"
    assert all("FR-03.01" not in e for e in gdt.check_orphan(manifest)[3])


def test_orphan_fanout_removed_only_is_flagged(tmp_path):
    """Direction 2 — a tag resolving only to a Removed FR is a confirmed orphan."""
    manifest = _build(tmp_path)
    orphan_frs = {o["tagged_fr"] for o in manifest["orphans"]}
    assert "FR-09.09" in orphan_frs
    status, sev, detail, ev, cmd = gdt.check_orphan(manifest)
    assert status == "fail"
    assert "FR-09.09" in detail
