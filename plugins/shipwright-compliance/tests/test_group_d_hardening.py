"""Coordinator hardening tests for the Group-D traceability detectives (TT2 revision).

Closes the fail-open / false-green holes the adversarial panel found, exercised over the
REAL ``build_manifest`` fan-out (not hand-built per-namespace-different manifests) so the
collector's un-namespaced tag fan-out is what's under test:

* MUST-FIX 1 — an UNKNOWN ``required_layers_source`` token is fail-closed (HARD), never
  silently advisory (``check_layer`` + ``refine_d1_covered``).
* MUST-FIX 2 — a display id shared across namespaces (active+active AND active+removed) is
  ambiguous: D-layer does not credit its ``ok`` and the RTM renders it ``?``.
* MUST-FIX 3 — ``check_orphan`` surfaces an unknown-category orphan; ``load_manifest``
  rejects a schema-invalid / unknown-enum manifest on READ.
* SHOULD-FIX 4/6 — ``invalid_tags`` surfaced; a skipped-evidence required layer → MISSING →
  D-layer HARD (explicit), end-to-end through ``build_manifest``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from scripts.audit import _group_d_traceability as gdt  # noqa: E402
from scripts.audit import group_d  # noqa: E402
from scripts.lib._rtm_layer_columns import layer_cells, load_layer_index  # noqa: E402
from scripts.lib.collectors.test_links import build_manifest  # noqa: E402

_TAGGED = ('import pytest\n\n@pytest.mark.covers("{fr}")\n'
           'def test_cov():\n    assert True\n')


def _spec(fr_rows: str, removed_rows: str = "") -> str:
    body = "# Spec\n\n| FR | Description | Priority | Layers |\n| --- | --- | --- | --- |\n" + fr_rows
    if removed_rows:
        body += "\n## Removed Requirements\n\n| FR | Description | Priority |\n| --- | --- | --- |\n" + removed_rows
    return body + "\n"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_collision(tmp_path, *, b_removed: bool):
    """FR-03.01 explicit+active in 01-a; in 02-b either active (active+active) or removed
    (active+removed). One test tagged @FR-03.01 with PASSING evidence, so the fanned link
    would yield ``coverage=ok`` in the active node(s) — the value we must NOT credit.

    Since manifest v3, the ACTIVE+ACTIVE form REFUSES to build: both specs claim key
    ``03::FR-03.01`` and the collector fails closed rather than dropping one. The
    ACTIVE+REMOVED form still builds — a tombstone is a legitimate state and is excluded
    from the collision rule (see ``_test_links_requirements``). Both are asserted below."""
    a, b = tmp_path / ".shipwright/planning/01-a", tmp_path / ".shipwright/planning/02-b"
    _write(a / "spec.md", _spec("| FR-03.01 | Live A | Must | unit |\n"))
    if b_removed:
        # 02-b carries ONLY the removed FR-03.01 (no other active FR to muddy the assertion).
        _write(b / "spec.md", _spec("", "| FR-03.01 | Old dup | Must |\n"))
    else:
        _write(b / "spec.md", _spec("| FR-03.01 | Live B | Must | unit |\n"))
    _write(tmp_path / "tests/test_cov.py", _TAGGED.format(fr="FR-03.01"))
    evidence = {"tests/test_cov.py::test_cov": {"status": "enabled", "executed": "pass"}}
    return build_manifest(
        tmp_path, spec_files=[a / "spec.md", b / "spec.md"],
        test_roots=[tmp_path / "tests"], evidence=evidence)


def _collided_manifest(*, b_removed: bool) -> dict:
    """The manifest the v2 collector USED to emit for ``_build_collision``.

    v3 prevents a generated manifest from ever carrying two ACTIVE nodes on one display
    id, so the ambiguity guard's remaining job is the HAND-EDITED / stale artifact — which
    is what this builds. Written out rather than generated precisely because the generator
    now refuses: pinning it here keeps the fan-out fail-closed behaviour covered instead
    of letting it quietly become untested when its natural input became unbuildable.

    The second key is ``02::FR-03.01`` — schema-VALID (it matches the v3 propertyNames
    pattern) but disagreeing with its own node id. A ``02-b::`` key would be far more
    obviously "hand-edited", and that is exactly why it is wrong here: it fails schema
    validation, so ``load_manifest`` returns None and D-orphan/D-layer SKIP. These tests
    call ``check_layer``/``check_orphan`` directly and would still pass — green over a
    path no real manifest can reach."""
    link = {"id": "tests/test_cov.py::test_cov", "path": "tests/test_cov.py::test_cov",
            "layer": "unit", "status": "enabled", "executed": "pass",
            "tag_source": "pytest_marker"}
    a = {"id": "FR-03.01", "spec_path": ".shipwright/planning/01-a/spec.md",
         "title": "Live A", "priority": "Must", "status": "active",
         "required_layers": ["unit"], "required_layers_source": "explicit",
         "tests": {"unit": [dict(link)]}, "coverage": {"unit": "ok"}}
    b = {**a, "spec_path": ".shipwright/planning/02-b/spec.md", "title": "Live B"}
    if b_removed:
        b = {**b, "status": "removed", "title": "Old dup",
             "tests": {}, "coverage": {"unit": "n/a"}}
    return {
        "schema_version": 3, "collector_version": "test", "generated_at": "t",
        "source_commit": "x", "spec_hash": "h",
        # Two nodes, one display id — only reachable by hand-editing under v3.
        "requirements": {"03::FR-03.01": a, "02::FR-03.01": b},
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
    }


# --- MUST-FIX 2: D-layer does not credit a fanned collision ok (real manifest) ----------


def test_dlayer_active_active_collision_ok_not_credited():
    manifest = _collided_manifest(b_removed=False)
    # sanity: the collector DID fan the passing tag into an active node as coverage ok.
    assert any(n["coverage"].get("unit") == "ok"
               for n in manifest["requirements"].values() if n["id"] == "FR-03.01")
    status, sev, detail, ev, cmd = gdt.check_layer(manifest)
    assert status == "pass"                                  # advisory (TT5-deferred)
    assert any("ambiguous_fanout" in e for e in ev)          # NOT silently credited


def test_dlayer_active_removed_collision_ok_not_credited():
    """Codex CRITICAL — an id ACTIVE in ns-A + REMOVED in ns-B is still a collision."""
    manifest = _collided_manifest(b_removed=True)
    status, sev, detail, ev, cmd = gdt.check_layer(manifest)
    assert status == "pass"
    assert any("ambiguous_fanout" in e for e in ev)


# --- MUST-FIX 2b: the RTM agrees with D-layer (renders ? not ok) -------------------------


def test_rtm_renders_collision_ok_as_ambiguous(tmp_path):
    manifest = _collided_manifest(b_removed=True)
    out = tmp_path / ".shipwright/compliance/test-traceability.json"
    _write(out, json.dumps(manifest))
    idx = load_layer_index(tmp_path)
    unit, _integration, _e2e = layer_cells(idx, "FR-03.01")
    assert unit == "?"                                       # not the fanned ok


def test_the_collided_fixture_is_schema_valid_so_the_guard_is_reachable(tmp_path):
    """FINDING 3 guard. The two ambiguity tests below call check_layer/check_orphan
    directly, so a schema-INVALID fixture would let them pass while the real path
    (load_manifest -> D-layer/D-orphan) SKIPped. Prove the artifact they pin is one
    load_manifest actually accepts."""
    _write(tmp_path / ".shipwright/compliance/test-traceability.json",
           json.dumps(_collided_manifest(b_removed=False)))
    loaded = gdt.load_manifest(tmp_path)
    assert loaded is not None, "fixture must be schema-valid or the guard is unreachable"
    assert sorted(loaded["requirements"]) == ["02::FR-03.01", "03::FR-03.01"]


def test_active_plus_removed_is_not_a_collision_and_keeps_the_live_node(tmp_path):
    """A tombstone in one split alongside a live row in another is a SUPPORTED state
    (_group_d_manifest: "REMOVED in ns-B is not a same-namespace duplicate"), and the
    campaign's own convention is that ids are stable and never renumbered (SPEC 3.1) --
    so "renumber one of the rows" would be wrong advice here. It must build, and the
    ACTIVE node must be the one that survives."""
    manifest = _build_collision(tmp_path, b_removed=True)
    assert list(manifest["requirements"]) == ["03::FR-03.01"]
    node = manifest["requirements"]["03::FR-03.01"]
    assert node["status"] == "active"                      # the live row, not the tombstone
    assert node["spec_path"].endswith("01-a/spec.md")


def test_two_specs_sharing_an_id_fail_closed_instead_of_dropping_a_node(tmp_path):
    """S3 regression guard. Under v2 the two splits produced TWO nodes (distinct
    path-derived keys). A v3 key is a pure function of the id, so they claim ONE — and
    resolving that by keeping either one would silently delete a requirement from the
    artifact whose job is to reveal traceability gaps. Generation must refuse."""
    import pytest  # noqa: PLC0415

    from scripts.lib.collectors._test_links_requirements import (  # noqa: PLC0415
        DuplicateRequirementId,
    )
    with pytest.raises(DuplicateRequirementId) as excinfo:
        _build_collision(tmp_path, b_removed=False)
    message = str(excinfo.value)
    assert "FR-03.01" in message
    # Actionable: it must name BOTH specs, or you cannot know which row to renumber.
    assert "01-a" in message and "02-b" in message


# --- MUST-FIX 2a: the fanned test is surfaced as a POSSIBLE orphan -----------------------


def test_orphan_fanout_active_removed_surfaced_as_possible():
    manifest = _collided_manifest(b_removed=True)
    status, sev, detail, ev, cmd = gdt.check_orphan(manifest)
    assert status == "fail"
    assert any("ambiguous_fanout" in e and "test_cov.py" in e for e in ev)
    assert sev == "LOW"                                      # possible, not confirmed


def test_orphan_removed_only_is_confirmed(tmp_path):
    """A tag resolving ONLY to a Removed FR (no active anywhere) is a confirmed orphan."""
    a = tmp_path / ".shipwright/planning/01-a"
    _write(a / "spec.md", _spec("| FR-01.01 | Live | Must | unit |\n",
                                "| FR-09.09 | Retired | Must |\n"))
    _write(tmp_path / "tests/test_dead.py",
           'import pytest\n\n@pytest.mark.covers("FR-09.09")\ndef test_dead():\n    assert True\n')
    manifest = build_manifest(tmp_path, spec_files=[a / "spec.md"],
                              test_roots=[tmp_path / "tests"], evidence={})
    assert {o["tagged_fr"] for o in manifest["orphans"]} == {"FR-09.09"}
    status, sev, detail, ev, cmd = gdt.check_orphan(manifest)
    assert status == "fail" and sev == "MEDIUM" and "FR-09.09" in detail


# --- SHOULD-FIX 6: R1 end-to-end — a skipped required-layer tag → MISSING → HARD ---------


def test_r1_skipped_evidence_makes_explicit_layer_hard_fail(tmp_path):
    a = tmp_path / ".shipwright/planning/01-a"
    _write(a / "spec.md", _spec("| FR-02.01 | Needs e2e | Must | e2e |\n"))
    _write(tmp_path / "e2e/flow.spec.ts",
           "import { test } from '@playwright/test';\n"
           "test('does x @FR-02.01', () => {});\n")
    evidence = {"e2e/flow.spec.ts::does x @FR-02.01":
                {"status": "skipped", "executed": "not_run"}}
    manifest = build_manifest(tmp_path, spec_files=[a / "spec.md"],
                              test_roots=[tmp_path / "e2e"], evidence=evidence)
    node = next(n for n in manifest["requirements"].values() if n["id"] == "FR-02.01")
    assert node["coverage"].get("e2e") == "MISSING"          # skipped ≠ covered (R1)
    status, sev, *_ = gdt.check_layer(manifest)
    assert status == "fail" and sev == "HIGH"                # explicit Must, no live e2e


# --- MUST-FIX 1: unknown provenance token is fail-closed HARD (pure) ---------------------


def _node(fr_id, *, source, coverage):
    return {"id": fr_id, "spec_path": "s", "title": fr_id, "priority": "Must",
            "status": "active", "required_layers": ["unit"],
            "required_layers_source": source, "tests": {}, "coverage": coverage}


def _manifest(nodes, **extra):
    # v3 keys derive the namespace from the id's group digits, not a split directory.
    m = {"schema_version": 3, "collector_version": "t", "generated_at": "t",
         "source_commit": "x", "spec_hash": "h",
         "requirements": {f"{n['id'][3:5]}::{n['id']}": n for n in nodes},
         "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": []}
    m.update(extra)
    return m


def test_dlayer_unknown_source_is_hard_not_advisory():
    """MUST-FIX 1 — a non-explicit, non-legacy token (rename/drift) missing a required
    layer is HARD (fail-closed), never silently advisory."""
    m = _manifest([_node("FR-01.01", source="post_rollout", coverage={"unit": "MISSING"})])
    status, sev, detail, ev, cmd = gdt.check_layer(m)
    assert status == "fail"
    assert any("post_rollout" in e for e in ev)


def test_dlayer_missing_source_key_is_hard_not_advisory():
    """FIX 1 — a node whose ``required_layers_source`` key is ABSENT routes to HARD (the
    default is a non-legacy sentinel), matching refine_d1_covered's None→fail-closed. This is
    a direct check_layer call (the real schema-valid path can't reach it — see the SKIP test
    below — but a future schema relaxation or any direct caller could)."""
    node = _node("FR-01.01", source="explicit", coverage={"unit": "MISSING"})
    node.pop("required_layers_source")  # key ABSENT
    status, sev, detail, ev, cmd = gdt.check_layer(_manifest([node]))
    assert status == "fail"                                   # HARD, not advisory
    assert any("__missing__" in e for e in ev)


def test_d1_explicit_source_requires_link(tmp_path):
    """FIX 2 (renamed) — proves what it actually exercises: an EXPLICIT-source FR with no
    executed-passing link is dropped from D1's covered set (requires-link path). The
    unknown/missing-token behaviour is pinned by the SKIP test + the check_layer tests."""
    from scripts.audit._group_d_traceability import refine_d1_covered  # noqa: PLC0415
    _write(tmp_path / ".shipwright/compliance/test-traceability.json",
           json.dumps(_manifest([_node("FR-01.01", source="explicit",
                                        coverage={"unit": "MISSING"})])))
    covered, note = refine_d1_covered({"FR-01.01"}, tmp_path)
    assert covered == set()                                  # explicit + no ok ⇒ dropped
    assert note == ""                                        # trusted manifest, no fallback


def test_out_of_vocab_source_is_rejected_on_read_and_d1_falls_back(tmp_path):
    """FIX 2 (real path) — an out-of-vocab ``required_layers_source`` makes the manifest
    schema-invalid, so ``load_manifest`` returns None: D-orphan/D-layer SKIP and D1 falls
    back to the event-proof — WITH a visible fallback note (FIX 3), because the manifest was
    PRESENT but untrusted (a green D1 must not silently hide the dropped link-proof)."""
    from scripts.audit._group_d_traceability import refine_d1_covered  # noqa: PLC0415
    bad = _manifest([_node("FR-01.01", source="post_rollout", coverage={"unit": "MISSING"})])
    _write(tmp_path / ".shipwright/compliance/test-traceability.json", json.dumps(bad))
    assert gdt.load_manifest(tmp_path) is None               # out-of-vocab enum rejected
    ids = {f.check_id: f for f in group_d.run(tmp_path, {}, None)}
    assert ids["D-orphan"].status == "skip" and ids["D-layer"].status == "skip"
    covered, note = refine_d1_covered({"FR-01.01"}, tmp_path)
    assert covered == {"FR-01.01"}                           # event-proof fallback
    assert "PRESENT but untrusted" in note                   # FIX 3: fallback made visible


def test_d1_absent_manifest_fallback_has_no_note(tmp_path):
    """FIX 3 — a genuinely ABSENT manifest (expected pre-TT8) falls back to event-proof
    SILENTLY (no note): absence is not a masked regression, unlike present-but-untrusted."""
    from scripts.audit._group_d_traceability import refine_d1_covered  # noqa: PLC0415
    covered, note = refine_d1_covered({"FR-01.01"}, tmp_path)  # no manifest written
    assert covered == {"FR-01.01"} and note == ""


# --- MUST-FIX 3: check_orphan unknown-category + load-time schema validation -------------


def test_orphan_unknown_category_is_surfaced():
    """MUST-FIX 3 — an orphan whose category is outside the known set is NOT dropped into
    the green branch."""
    m = _manifest([], orphans=[{"test": "t.py::t", "tagged_fr": "FR-09.09",
                                "reason": "fr_removed", "category": "weird_new_bucket"}])
    status, sev, detail, ev, cmd = gdt.check_orphan(m)
    assert status == "fail"
    assert any("t.py::t" in e for e in ev)


def test_load_manifest_rejects_schema_invalid_enum(tmp_path):
    """MUST-FIX 3 — a hand-edited manifest with an out-of-vocab enum is rejected on READ
    (skip, never trusted)."""
    bad = _manifest([_node("FR-01.01", source="explicit", coverage={"unit": "totally_bogus"})])
    _write(tmp_path / ".shipwright/compliance/test-traceability.json", json.dumps(bad))
    assert gdt.load_manifest(tmp_path) is None
    ids = {f.check_id: f for f in group_d.run(tmp_path, {}, None)}
    assert ids["D-orphan"].status == "skip" and ids["D-layer"].status == "skip"


def test_orphan_surfaces_invalid_tags():
    """SHOULD-FIX 4 — a malformed @FR tag (silent under-coverage) is a hygiene finding."""
    m = _manifest([], invalid_tags=[{"test": "t.py::t", "raw": "@FR-1.3",
                                     "reason": "non_canonical_fr_id"}])
    status, sev, detail, ev, cmd = gdt.check_orphan(m)
    assert status == "fail"
    assert any("@FR-1.3" in e for e in ev)
