"""F4 must bound an ADR at the next heading, not only at the next ADR header.

GitHub issue #931: a ``## `` section or a block of ``### DR-NNN:`` design
decisions written after a short ADR was counted as that ADR's body, so the
short ADR was reported as bloated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_f  # noqa: E402


def _write_log(root: Path, text: str) -> None:
    doc = root / ".shipwright" / "agent_docs"
    doc.mkdir(parents=True, exist_ok=True)
    (doc / "decision_log.md").write_text(text, encoding="utf-8")


def _f4(root: Path):
    return next(f for f in group_f.run(root, None, None) if f.check_id == "F4")


def _lines(prefix: str, n: int) -> str:
    return "\n".join(f"{prefix} {i}" for i in range(n))


@pytest.mark.covers("FR-01.10")
def test_section_after_adr_is_not_part_of_the_adr(tmp_path: Path):
    _write_log(tmp_path, "\n".join([
        "# Decision Log", "",
        "### ADR-005: Short", _lines("adr", 10), "",
        "## Design decisions (design phase)",
        "### DR-001: first", _lines("dr", 40),
        "### DR-002: second", _lines("dr", 40), "",
        "### ADR-006: Next", _lines("adr", 5), "",
    ]))
    assert _f4(tmp_path).status == "pass"


@pytest.mark.covers("FR-01.10")
def test_non_adr_h3_block_at_end_of_file_is_not_part_of_the_last_adr(tmp_path: Path):
    _write_log(tmp_path, "\n".join([
        "### ADR-001: Short", _lines("adr", 10), "",
        "### DR-001: tail", _lines("dr", 90), "",
    ]))
    assert _f4(tmp_path).status == "pass"


@pytest.mark.covers("FR-01.10")
def test_genuinely_bloated_adr_still_fails(tmp_path: Path):
    _write_log(tmp_path, "\n".join([
        "### ADR-002: Long", _lines("adr", 80), "",
        "## Another section", _lines("x", 3),
    ]))
    f4 = _f4(tmp_path)
    assert f4.status == "fail"
    assert "ADR-002" in f4.detail


@pytest.mark.covers("FR-01.10")
def test_subheadings_below_h3_stay_inside_the_adr(tmp_path: Path):
    _write_log(tmp_path, "\n".join([
        "### ADR-003: Long with sub-headings", _lines("adr", 40),
        "#### Context", _lines("c", 30), "",
    ]))
    assert _f4(tmp_path).status == "fail"


@pytest.mark.covers("FR-01.10")
def test_hash_comments_inside_a_code_fence_do_not_end_the_adr(tmp_path: Path):
    _write_log(tmp_path, "\n".join([
        "### ADR-004: Long with a code block", _lines("adr", 30),
        "```bash", "# install deps", "## step two", "### not a heading", "```",
        _lines("adr", 40), "",
    ]))
    f4 = _f4(tmp_path)
    assert f4.status == "fail"
    assert "ADR-004" in f4.detail
