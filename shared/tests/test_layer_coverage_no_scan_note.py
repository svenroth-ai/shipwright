"""The cross-layer gate must not blame missing tests when no test was ever scanned (#972).

Its failure text asked the author to "add an executed-passing test at the missing layer(s)".
When the regenerated manifest links no tagged test at all (the collector looked in no folder, or
no file carried an ``@FR`` tag) that advice points at the wrong fix: the tests exist, the
collector never saw them. In that case the text now names ``traceability.test_roots`` instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import pytest  # noqa: E402
import tools.verifiers.layer_coverage as _lc  # noqa: E402
from tools.verifiers._layer_coverage_core import CrossLayerVerdict, LayerGap  # noqa: E402


def _head(*, links: int = 0, orphans=(), untagged=()):
    tests = {"unit": [{"path": f"t{i}.py::test_x"} for i in range(links)]} if links else {}
    return {
        "requirements": {"a::FR-09.01": {"id": "FR-09.01", "status": "active", "tests": tests}},
        "orphans": list(orphans), "untagged_tests": list(untagged),
    }


def _failing_verdict() -> CrossLayerVerdict:
    gap = LayerGap("FR-09.01", "a::FR-09.01", "unit", "Must", "explicit", "MISSING")
    return CrossLayerVerdict(changed_keys=["a::FR-09.01"], hard=[gap])


@pytest.mark.covers("FR-01.10/AC01")
def test_no_linked_test_anywhere_points_at_test_roots_not_at_new_tests():
    note = _lc._no_scan_note(_head())
    result = _lc._cross_layer_result("cross-layer", _failing_verdict(), note)
    assert result.ok is False
    assert "traceability.test_roots" in result.detail
    assert "links no test at all" in result.detail
    # Conditional, not a replacement: an existing-but-empty test folder is not a wrong-folder
    # problem, so the original advice stays available for a project that really has no test yet.
    assert "If the project really has no test there yet" in result.detail
    assert "add an executed-passing test" in result.detail


@pytest.mark.covers("FR-01.10/AC01")
def test_a_linked_test_keeps_the_original_advice():
    note = _lc._no_scan_note(_head(links=1))
    assert note == ""
    result = _lc._cross_layer_result("cross-layer", _failing_verdict(), note)
    assert "add an executed-passing test" in result.detail
    assert "traceability.test_roots" not in result.detail


@pytest.mark.covers("FR-01.10/AC01")
@pytest.mark.parametrize("head", [
    _head(orphans=["x.py::test_o"]),
    _head(untagged=["x.py::test_u"]),
    {**_head(), "invalid_tags": [{"test": "x.py::test_i", "tag": "@FR-bogus"}]},
])
def test_an_orphan_untagged_or_badly_tagged_test_proves_files_were_scanned(head):
    assert _lc._no_scan_note(head) == ""  # the collector did see test files; the fix is the tag


class _FakeCtx:  # stands in for git_context(): the repo exists, so the gate is enforcing
    pass


@pytest.mark.covers("FR-01.10/AC01")
@pytest.mark.parametrize("head, base, expect_note", [
    (_head(), {}, True),
    (_head(links=1), {}, False),
    (_head(), _head(links=1), True),   # a linked BASE must not mask an empty HEAD
    (_head(links=1), _head(), False),  # ...and an empty BASE must not trigger the note
])
def test_check_cross_layer_coverage_wires_the_head_manifest_into_the_note(
    monkeypatch, tmp_path, head, base, expect_note,
):
    """The note is computed from the HEAD manifest, only on a failing verdict, inside the gate."""
    monkeypatch.setattr(_lc, "_complexity", lambda *_a: "medium")
    monkeypatch.setattr(_lc, "_is_enforcing", lambda _c: True)
    monkeypatch.setattr(_lc, "_git_precheck", lambda *_a: None)
    monkeypatch.setattr(_lc, "regenerate_base_head", lambda *_a, **_k: (base, head, {}))
    monkeypatch.setattr(_lc, "changed_criteria_ids", lambda *_a: (set(), None))
    monkeypatch.setattr(_lc, "evaluate_cross_layer", lambda *_a: _failing_verdict())
    result = _lc.check_cross_layer_coverage(tmp_path, "run-1", "abc1234")
    assert result.ok is False
    assert ("traceability.test_roots" in result.detail) is expect_note
    assert "add an executed-passing test" in result.detail  # the original advice is never dropped


@pytest.mark.covers("FR-01.10/AC01")
def test_the_gate_regen_resolves_roots_silently_on_its_throwaway_archive():
    """`_build` runs on temp archives: it must pass warn=False (no stderr line naming a temp dir)."""
    import tools.verifiers._layer_coverage_regen as regen

    seen: dict = {}

    class _Io:
        @staticmethod
        def configured_test_roots(root, **kwargs):
            seen.update(kwargs)
            return []

        default_test_roots = staticmethod(lambda root: [])
        discover_specs = staticmethod(lambda root: [])
        configured_prune_dirs = staticmethod(lambda root: frozenset())

    class _Links:
        build_manifest = staticmethod(lambda *a, **k: {})

    regen._build(_Links, _Io, Path("."), {}, "abc")
    assert seen == {"warn": False}


@pytest.mark.covers("FR-01.10/AC01")
@pytest.mark.parametrize("head", [{}, {"requirements": None}, {"requirements": {"k": "junk"}}])
def test_a_malformed_manifest_never_crashes_the_note(head):
    assert isinstance(_lc._no_scan_note(head), str)


@pytest.mark.covers("FR-01.10/AC01")
def test_default_argument_keeps_every_other_caller_unchanged():
    result = _lc._cross_layer_result("cross-layer", _failing_verdict())
    assert "add an executed-passing test" in result.detail
