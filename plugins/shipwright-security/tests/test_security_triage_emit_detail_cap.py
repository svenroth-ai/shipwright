"""A finding with a huge scanner description truncates instead of vanishing.

iterate-2026-08-13-triage-detail-selfcap, security half — see
``shared/tests/test_triage_detail_selfcap.py`` for the shared-scope sites and
the full defect writeup. ``emit_findings_to_triage`` built ``detail`` by
joining ``affected_file:line``, the raw scanner ``description``, and an
optional ``fix:`` note with no self-cap, so a scanner that hands back a huge
verbatim ``description`` could raise ``ValueError`` inside the per-finding
best-effort ``except Exception`` and the finding was silently dropped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
_SHARED_SCRIPTS = PLUGIN_ROOT.parents[1] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from security_triage_emit import _DETAIL_MAX_LEN, emit_findings_to_triage  # noqa: E402
from triage import read_all_items  # noqa: E402


def _finding(*, description: str = "d") -> dict:
    return {
        "source": "semgrep", "rule": "r1", "affected_file": "a.py",
        "affected_line": 1, "description": description, "severity": "high",
    }


def _pad_to(tmp_path: Path, target: int) -> None:
    """A finding whose rendered detail is exactly ``target`` characters."""
    probe = "a.py:1 | d"
    pad_len = target - len(probe) + 1
    emit_findings_to_triage(tmp_path, [_finding(description="d" * pad_len)])


@pytest.mark.parametrize(
    "length,expect_truncated",
    [
        (_DETAIL_MAX_LEN - 1, False),
        (_DETAIL_MAX_LEN, False),
        (_DETAIL_MAX_LEN + 1, True),
    ],
)
def test_detail_boundary(tmp_path: Path, length: int, expect_truncated: bool) -> None:
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")  # F7: marker req'd
    _pad_to(tmp_path, length)
    [item] = read_all_items(tmp_path)
    assert item["detail"].endswith("…") is expect_truncated
    assert len(item["detail"]) == min(length, _DETAIL_MAX_LEN)


def test_detail_is_capped_for_a_huge_description(tmp_path: Path) -> None:
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")  # F7: marker req'd
    appended = emit_findings_to_triage(tmp_path, [_finding(description="x" * 20000)])
    assert appended == 1
    [item] = read_all_items(tmp_path)
    assert len(item["detail"]) == _DETAIL_MAX_LEN
    assert item["detail"].endswith("…")
    assert len(item["detail"]) <= 6000


def test_detail_untouched_for_an_ordinary_finding(tmp_path: Path) -> None:
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")  # F7: marker req'd
    emit_findings_to_triage(tmp_path, [_finding(description="short desc")])
    [item] = read_all_items(tmp_path)
    assert not item["detail"].endswith("…")
    assert item["detail"] == "a.py:1 | short desc"
