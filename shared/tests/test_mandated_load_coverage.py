"""Unit tests for lib.mandated_load_coverage.check_coverage (TC3.2, trg-c0d83dce)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.mandated_load_coverage import READ_LINE_CAP, check_coverage


def _write_lines(path: Path, n: int) -> None:
    path.write_text("\n".join(f"line {i}" for i in range(n)) + "\n", encoding="utf-8")


def test_file_within_cap_reports_exceeds_cap_false(tmp_path: Path) -> None:
    small = tmp_path / "spec.md"
    _write_lines(small, 10)
    result = check_coverage([str(small)])
    assert result == {
        "files": [{
            "path": str(small), "exists": True,
            "total_lines": 10, "cap_lines": READ_LINE_CAP, "exceeds_cap": False,
        }],
        "any_exceeds_cap": False,
    }


def test_file_over_cap_reports_exceeds_cap_true(tmp_path: Path) -> None:
    big = tmp_path / "decision_log.md"
    _write_lines(big, READ_LINE_CAP + 1)
    result = check_coverage([str(big)])
    assert result["files"][0]["total_lines"] == READ_LINE_CAP + 1
    assert result["files"][0]["exceeds_cap"] is True
    assert result["any_exceeds_cap"] is True


def test_file_exactly_at_cap_does_not_exceed(tmp_path: Path) -> None:
    exact = tmp_path / "spec.md"
    _write_lines(exact, READ_LINE_CAP)
    result = check_coverage([str(exact)])
    assert result["files"][0]["exceeds_cap"] is False


def test_missing_file_reports_exists_false_not_a_crash(tmp_path: Path) -> None:
    missing = tmp_path / "nope.md"
    result = check_coverage([str(missing)])
    assert result["files"] == [{"path": str(missing), "exists": False}]
    assert result["any_exceeds_cap"] is False


def test_one_oversized_file_among_several_sets_the_aggregate_flag(tmp_path: Path) -> None:
    small = tmp_path / "a" / "spec.md"
    big = tmp_path / "b" / "spec.md"
    small.parent.mkdir()
    big.parent.mkdir()
    _write_lines(small, 5)
    _write_lines(big, READ_LINE_CAP + 5)
    result = check_coverage([str(small), str(big)])
    assert result["any_exceeds_cap"] is True
    assert result["files"][0]["exceeds_cap"] is False
    assert result["files"][1]["exceeds_cap"] is True


def test_custom_cap_lines_is_respected(tmp_path: Path) -> None:
    f = tmp_path / "spec.md"
    _write_lines(f, 50)
    result = check_coverage([str(f)], cap_lines=10)
    assert result["files"][0]["cap_lines"] == 10
    assert result["files"][0]["exceeds_cap"] is True


def test_unreadable_file_is_declared_not_raised(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "spec.md"
    _write_lines(f, 5)

    def _raise_open(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "open", _raise_open)
    result = check_coverage([str(f)])
    assert result["files"] == [{
        "path": str(f), "exists": True, "error": "permission denied",
        "total_lines": None, "cap_lines": READ_LINE_CAP, "exceeds_cap": None,
    }]
    assert result["any_exceeds_cap"] is False


def test_empty_paths_list_returns_no_files_and_no_overflow() -> None:
    assert check_coverage([]) == {"files": [], "any_exceeds_cap": False}


@pytest.mark.parametrize("total_lines", [1, READ_LINE_CAP, READ_LINE_CAP + 1])
def test_total_lines_matches_actual_line_count(tmp_path: Path, total_lines: int) -> None:
    f = tmp_path / "spec.md"
    _write_lines(f, total_lines)
    result = check_coverage([str(f)])
    assert result["files"][0]["total_lines"] == total_lines
