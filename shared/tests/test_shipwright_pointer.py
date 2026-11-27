"""The root pointer stub recogniser (campaign root-files-into-config, R1a; BRIEF 11.5 + 14.1/14.2)."""

from __future__ import annotations

import inspect
import random
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts", _SHARED / "testkit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib import shipwright_pointer as sptr  # noqa: E402
from pointer_stub_cases import MAX, cases  # noqa: E402

CASES = cases()


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_every_shared_fixture_row_gets_its_verdict(case):
    assert sptr.classify(case.data).kind == case.expect, case.why


@pytest.mark.covers("FR-01.11")
def test_the_fixture_table_covers_every_brief_14_1_case_and_every_verdict():
    ids = {c.id for c in CASES}
    required = {"lf_canonical", "crlf", "bom", "trailing_spaces", "exactly_512", "size_513",
                "version_2", "signature_on_line_2", "empty", "non_utf8", "conflict_on_line_1",
                "conflict_after_signature", "json_after_signature", "stub_at_new_path"}
    assert required <= ids and len(ids) == len(CASES)
    assert {c.expect for c in CASES} == {sptr.STUB, sptr.TOO_NEW, sptr.EDITED, sptr.NOT_STUB}
    sizes = {c.id: len(c.data.replace(b"\r", b"")) for c in CASES}
    assert sizes["exactly_512"] == sizes["bom_512"] == sizes["crlf_512_after_strip"] == MAX
    assert sizes["size_513"] == sizes["bom_513"] == MAX + 1


@pytest.mark.covers("FR-01.11")
def test_versions_are_reported():
    assert sptr.classify(b"SHIPWRIGHT-POINTER/1\n") == sptr.Verdict("stub", 1)
    assert sptr.classify(b"SHIPWRIGHT-POINTER/7\n") == sptr.Verdict("too_new", 7)
    assert sptr.classify(b"{}") == sptr.Verdict("not_stub", None)


@pytest.mark.covers("FR-01.11")
def test_classify_is_total_on_arbitrary_input():
    rng = random.Random(1127)
    blobs = [bytes(rng.randrange(256) for _ in range(rng.randrange(0, 700))) for _ in range(400)]
    blobs += [b"SHIPWRIGHT-POINTER/1\n" + b for b in blobs[:100]]
    blobs += [b"\xef\xbb\xbf" + b for b in blobs[:100]] + [b"\r" * 600, b"\n" * 600]
    for blob in blobs:
        assert sptr.classify(blob).kind in {sptr.STUB, sptr.TOO_NEW, sptr.EDITED, sptr.NOT_STUB}
    assert sptr.classify(None).kind == sptr.NOT_STUB  # type: ignore[arg-type]
    assert sptr.classify("SHIPWRIGHT-POINTER/1").kind == sptr.NOT_STUB  # type: ignore[arg-type]


@pytest.mark.covers("FR-01.11")
def test_render_round_trips_and_keeps_the_11_5_shape():
    data = sptr.render("0.40.0")
    assert sptr.classify(data) == sptr.Verdict("stub", 1)
    assert len(data) <= MAX and data.isascii() and b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")
    lines = data.decode().split("\n")
    assert lines[:3] == ["SHIPWRIGHT-POINTER/1", "moved_to: .shipwright/config/", "min_plugin_version: 0.40.0"]
    assert data.endswith(b"\n") and b"{" not in data  # no trailing JSON (11.5)
    assert sptr.classify(sptr.render("1.2.3-rc.1+build.5")).kind == sptr.STUB


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("bad", ["", "0.40", "v0.40.0", "0.40.0\nmoved_to: /etc/", "0.40.0 ", "0.4¹.0",
                                 "0.40.0-" + "x" * 600, None, 40, "01.2.3", "1.2.3-01", "1.2.3+build..5", "1.2.3-"])
def test_render_refuses_anything_but_a_semver_string(bad):
    with pytest.raises(ValueError):
        sptr.render(bad)  # type: ignore[arg-type]


@pytest.mark.covers("FR-01.11")
def test_nothing_in_the_module_returns_or_follows_a_path_from_the_stub():
    """BRIEF 14.2: ``moved_to`` is human text. The public API is the recogniser and the renderer."""
    public = {n for n, o in vars(sptr).items() if callable(o) and not n.startswith("_")
              and getattr(o, "__module__", None) == sptr.__name__}
    assert public == {"classify", "render", "Verdict"}
    src = inspect.getsource(sptr)
    assert "moved_to" not in src.split("def render", 1)[0].split('"""', 2)[2]  # only the docstring + render
    assert "Path(" not in src and "open(" not in src
