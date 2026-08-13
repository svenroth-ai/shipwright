"""A large compliance-finding set truncates instead of vanishing.

iterate-2026-08-13-triage-detail-selfcap, compliance half — see
``shared/tests/test_triage_detail_selfcap.py`` for the shared-scope sites and
the full defect writeup. ``triage_bundle_render.build_detail`` (imported into
``scripts.audit.triage_bundle``) built ``detail`` via an unbounded per-finding
loop/join with no self-cap, so a large-enough finding set raised ``ValueError``
inside ``triage_bundle``'s best-effort ``except Exception`` and the backlog
item was silently dropped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
_SHARED_SCRIPTS = _PLUGIN_ROOT.parents[1] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from scripts.audit import triage_bundle_render as render  # noqa: E402
from triage import append_triage_item_idempotent, read_all_items  # noqa: E402


def _fail(i: int) -> dict:
    return {"key": f"C{i}", "name": "x" * 60, "detail": "y" * 60}


def test_build_detail_truncates_when_over_cap() -> None:
    detail = render.build_detail([_fail(i) for i in range(500)])
    assert len(detail) == render._DETAIL_MAX_LEN
    assert detail.endswith("…")


def test_build_detail_untouched_under_cap() -> None:
    detail = render.build_detail([_fail(1)])
    assert not detail.endswith("…")
    assert "C1" in detail


def _pad_to(target: int) -> list[dict]:
    """One finding whose rendered detail is exactly ``target`` characters."""
    probe = render.build_detail([{"key": "k", "name": "n", "detail": ""}])
    pad_len = target - len(probe) + 1
    return [{"key": "k", "name": "n" * pad_len, "detail": ""}]


@pytest.mark.parametrize(
    "length,expect_truncated",
    [
        (render._DETAIL_MAX_LEN - 1, False),
        (render._DETAIL_MAX_LEN, False),
        (render._DETAIL_MAX_LEN + 1, True),
    ],
)
def test_build_detail_boundary(length: int, expect_truncated: bool) -> None:
    detail = render.build_detail(_pad_to(length))
    assert detail.endswith("…") is expect_truncated
    assert len(detail) == min(length, render._DETAIL_MAX_LEN)


def test_build_detail_feeds_a_write_that_no_longer_raises(tmp_path: Path) -> None:
    """The regression itself: a finding set large enough to blow past
    append_triage_item's 6000-char cap used to raise ValueError and drop the
    item. It must now append, truncated."""
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")  # F7: marker req'd
    fails = [_fail(i) for i in range(500)]
    new_id = append_triage_item_idempotent(
        tmp_path, source="compliance", severity="medium", kind="improvement",
        title="t", detail=render.build_detail(fails),
        dedup_key="compliance:backlog:huge", match_commit=False, window_seconds=None,
    )
    assert new_id is not None
    [item] = read_all_items(tmp_path)
    assert len(item["detail"]) <= 6000
