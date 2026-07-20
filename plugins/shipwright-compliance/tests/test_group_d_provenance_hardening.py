"""Group-D hardening: provenance tokens and load-time schema validation.

Split out of ``test_group_d_hardening.py``, which S3 grew to 332 lines — past
the 300 cap and NOT in ``shipwright_bloat_baseline.json``, so CI's anti-ratchet
(which only blocks ratcheting EXISTING entries) let it through and it was headed
for a Group-H finding post-merge. Split rather than baselined: baselining a file
the previous step just wrote is the hook bypass the checklist names.

The seam is cohesive, not arbitrary. Everything here operates on a HAND-BUILT
manifest and asks "does the coordinator trust what it just read?" — unknown
provenance tokens, absent keys, out-of-vocab enums, unknown orphan categories,
malformed tags. Its sibling exercises the REAL ``build_manifest`` fan-out and
asks a different question: "does a display id shared across namespaces get
credited?" Different fixtures, different failure mode, no shared state.

* MUST-FIX 1 — an UNKNOWN ``required_layers_source`` token is fail-closed
  (HARD), never silently advisory (``check_layer`` + ``refine_d1_covered``).
* MUST-FIX 3 — ``check_orphan`` surfaces an unknown-category orphan;
  ``load_manifest`` rejects a schema-invalid / unknown-enum manifest on READ.
* SHOULD-FIX 4 — ``invalid_tags`` surfaced as a hygiene finding.
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


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


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


# --- MUST-FIX 1: unknown provenance token is fail-closed HARD (pure) ---------------------


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
