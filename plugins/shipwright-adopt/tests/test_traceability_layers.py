"""TT7 — adopt ``required_layers`` ambiguity resolution (``traceability_layers``).

Unit tests for the predeclared-decision resolver + the spec ``Layers`` write-back, incl.
the doubt-review robustness fixes (MED#1): escaped-pipe/mis-column safety, CRLF
preservation, and idempotent re-adopt. Imported by BARE name off ``scripts/lib`` (ADR-045)
so this test never binds ``sys.modules['lib']``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parent.parent
_REPO = _PLUGIN.parents[1]
sys.path.insert(0, str(_PLUGIN / "scripts" / "lib"))

import traceability_layers as tl  # noqa: E402

_MINI_SPEC = (
    _REPO / "plugins" / "shipwright-compliance" / "tests" / "fixtures"
    / "traceability" / "mini_repos" / "app" / "spec.md"
)
_DECISIONS = (
    _REPO / "plugins" / "shipwright-compliance" / "tests" / "fixtures"
    / "traceability" / "decisions" / "adopt_ambiguity.json"
)


# --------------------------------------------------------------------------- #
# find_ambiguous_frs                                                          #
# --------------------------------------------------------------------------- #

def test_find_ambiguous_flags_empty_cells_not_explicit_or_removed():
    amb = tl.find_ambiguous_frs(_MINI_SPEC.read_text(encoding="utf-8"), "app")
    keys = {a["key"] for a in amb}
    # FR-03.02 + FR-03.03 have empty Layers cells → ambiguous.
    assert keys == {"app::FR-03.02", "app::FR-03.03"}
    # FR-03.01 (explicit `unit, e2e`) + FR-03.09 (removed) are NOT ambiguous.
    assert "app::FR-03.01" not in keys
    assert "app::FR-03.09" not in keys


def test_find_ambiguous_flags_adopt_inferred_marker_cells():
    spec = (
        "## Functional Requirements\n"
        "| ID | Name | Priority | Description | Source | Layers |\n"
        "|----|------|----------|-------------|--------|--------|\n"
        "| FR-01.01 | A | Must | d | `s` | unit, e2e (inferred) |\n"
        "| FR-01.02 | B | Must | d | `s` | unit, integration |\n"  # author-explicit
    )
    amb = tl.find_ambiguous_frs(spec, "01-adopted")
    keys = {a["key"] for a in amb}
    assert keys == {"01-adopted::FR-01.01"}  # only the (inferred) one


# --------------------------------------------------------------------------- #
# resolve_layer_ambiguities — the binding "never stall" contract              #
# --------------------------------------------------------------------------- #

def test_resolve_uses_predeclared_decision_when_present():
    amb = tl.find_ambiguous_frs(_MINI_SPEC.read_text(encoding="utf-8"), "app")
    res = {r.key: r for r in tl.resolve_layer_ambiguities(amb, tl.load_decisions(_DECISIONS))}
    assert res["app::FR-03.02"].required_layers == ["e2e"]
    assert res["app::FR-03.02"].provenance == "inferred_legacy"
    assert res["app::FR-03.02"].resolved_from == "predeclared_decision"
    assert res["app::FR-03.03"].provenance == "defaulted_legacy"
    assert all(r.resolved_from == "predeclared_decision" for r in res.values())


def test_resolve_never_stalls_without_a_fixture():
    # No decisions fixture (real unattended adopt) → every FR still resolves, deferring
    # to the collector's inference. Total function, no prompt, no exception.
    amb = tl.find_ambiguous_frs(_MINI_SPEC.read_text(encoding="utf-8"), "app")
    res = tl.resolve_layer_ambiguities(amb, {})
    assert len(res) == len(amb)
    assert all(r.resolved_from == "inference_default" for r in res)
    assert all(r.required_layers == [] for r in res)


def test_load_decisions_tolerates_missing_and_malformed(tmp_path: Path):
    assert tl.load_decisions(None) == {}
    assert tl.load_decisions(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert tl.load_decisions(bad) == {}
    assert set(tl.load_decisions(_DECISIONS)) == {"app::FR-03.02", "app::FR-03.03"}


# --------------------------------------------------------------------------- #
# apply_layer_decisions_to_spec — write-back robustness (doubt MED#1)          #
# --------------------------------------------------------------------------- #

def test_apply_decisions_writes_layers_back_to_spec(tmp_path: Path):
    # A predeclared decision must reach the spec BEFORE Step F, else it is discarded (O1).
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Functional Requirements\n"
        "| FR | Description | Priority | Layers |\n"
        "|----|-------------|----------|--------|\n"
        "| FR-03.01 | Sign in | Must | unit, e2e |\n"       # explicit — untouched
        "| FR-03.02 | Dashboard | Must | |\n",              # ambiguous — decided
        encoding="utf-8")
    amb = tl.find_ambiguous_frs(spec.read_text(encoding="utf-8"), "app")
    res = tl.resolve_layer_ambiguities(amb, tl.load_decisions(_DECISIONS))
    assert tl.apply_layer_decisions_to_spec(spec, res) == 1
    body = spec.read_text(encoding="utf-8")
    assert "| FR-03.02 | Dashboard | Must | e2e (inferred) |" in body
    assert "| FR-03.01 | Sign in | Must | unit, e2e |" in body  # explicit row untouched
    # inference_default resolutions (no fixture) write nothing.
    assert tl.apply_layer_decisions_to_spec(spec, tl.resolve_layer_ambiguities(amb, {})) == 0


def test_apply_decisions_does_not_mis_column_a_piped_description(tmp_path: Path):
    # A Description with an ESCAPED pipe must not shift columns (clobber Source) nor drop
    # the `\|` escaping.
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Functional Requirements\n"
        "| ID | Name | Priority | Description | Source | Layers |\n"
        "|----|------|----------|-------------|--------|--------|\n"
        "| FR-01.02 | Filter | Must | filter by status \\| priority | `app/f.py` | |\n",
        encoding="utf-8")
    amb = tl.find_ambiguous_frs(spec.read_text(encoding="utf-8"), "01-adopted")
    res = tl.resolve_layer_ambiguities(amb, {"01-adopted::FR-01.02": {
        "decision": "inferred_legacy", "required_layers": ["e2e"]}})
    assert tl.apply_layer_decisions_to_spec(spec, res) == 1
    body = spec.read_text(encoding="utf-8")
    assert "filter by status \\| priority" in body   # escape preserved, not split
    assert "`app/f.py`" in body                       # Source column NOT clobbered
    assert "e2e (inferred)" in body                   # written into the Layers column


def test_apply_decisions_skips_a_miscolumned_unescaped_pipe_row(tmp_path: Path):
    # An UN-escaped pipe shifts the cell count != header → the row is guarded (left alone),
    # never mis-written.
    spec = tmp_path / "spec.md"
    original = (
        "## Functional Requirements\n"
        "| ID | Name | Priority | Description | Source | Layers |\n"
        "|----|------|----------|-------------|--------|--------|\n"
        "| FR-01.02 | Filter | Must | status | priority | `app/f.py` | |\n"
    )
    spec.write_text(original, encoding="utf-8")
    amb = tl.find_ambiguous_frs(spec.read_text(encoding="utf-8"), "01-adopted")
    assert amb == []                                  # mis-columned row not classified
    res = tl.resolve_layer_ambiguities(
        [{"key": "01-adopted::FR-01.02", "id": "FR-01.02", "title": "Filter"}],
        {"01-adopted::FR-01.02": {"decision": "inferred_legacy", "required_layers": ["e2e"]}})
    assert tl.apply_layer_decisions_to_spec(spec, res) == 0
    assert spec.read_text(encoding="utf-8") == original  # untouched


def test_apply_decisions_preserves_crlf_and_is_idempotent(tmp_path: Path):
    # A Windows-authored (CRLF) spec must not be LF-normalised, and a re-adopt with an
    # already-resolved cell must write NOTHING.
    spec = tmp_path / "spec.md"
    spec.write_bytes(
        ("## Functional Requirements\r\n"
         "| ID | Name | Priority | Layers |\r\n"
         "|----|------|----------|--------|\r\n"
         "| FR-01.02 | Dash | Must | |\r\n").encode("utf-8"))
    amb = tl.find_ambiguous_frs(spec.read_bytes().decode("utf-8"), "01-adopted")
    res = tl.resolve_layer_ambiguities(amb, {"01-adopted::FR-01.02": {
        "decision": "inferred_legacy", "required_layers": ["e2e"]}})
    assert tl.apply_layer_decisions_to_spec(spec, res) == 1
    raw = spec.read_bytes()
    assert b"\r\n" in raw and b"e2e (inferred)" in raw
    assert b"\n\n" not in raw.replace(b"\r\n", b"X")   # no bare LF introduced
    # Re-run: the cell is already `e2e (inferred)` → idempotent, no churn.
    assert tl.apply_layer_decisions_to_spec(spec, res) == 0
    assert spec.read_bytes() == raw
