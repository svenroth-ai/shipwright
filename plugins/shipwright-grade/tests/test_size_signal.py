"""Tests for size_signal — the local oversize-file ratio (maintainability proxy)."""

from __future__ import annotations

from pathlib import Path

from conftest import build_repo
from repo_context import RepoContext
from resolve_target import resolve_target
from size_signal import compute_size_signal


def _ctx(root: Path) -> RepoContext:
    return RepoContext(resolve_target(str(root)))


def _small(n: int = 5) -> str:
    return "\n".join(f"x = {i}" for i in range(n)) + "\n"


def _big(lines: int = 400) -> str:
    return "\n".join(f"line_{i} = {i}" for i in range(lines)) + "\n"


def test_all_small_source_is_zero_ratio(tmp_path):
    root = build_repo(tmp_path / "r", [
        {"subject": "feat: code (#1)",
         "files": {"a.py": _small(), "b.py": _small(), "pkg/c.py": _small()}},
    ])
    sig = compute_size_signal(_ctx(root))
    assert sig.measurable is True
    assert sig.files_total == 3 and sig.files_over == 0
    assert sig.ratio == 0.0
    assert sig.detail == "0/3 source files over 300 LOC"


def test_oversize_files_counted(tmp_path):
    root = build_repo(tmp_path / "r", [
        {"subject": "feat: code (#1)",
         "files": {"small.py": _small(), "huge1.py": _big(), "huge2.py": _big()}},
    ])
    sig = compute_size_signal(_ctx(root))
    assert (sig.files_over, sig.files_total) == (2, 3)
    assert abs(sig.ratio - 2 / 3) < 1e-9


def test_threshold_boundary_is_strict_greater_than(tmp_path):
    # Exactly 300 lines is NOT over threshold; 301 is.
    root = build_repo(tmp_path / "r", [
        {"subject": "feat (#1)",
         "files": {"exact.py": _big(300), "over.py": _big(301)}},
    ])
    sig = compute_size_signal(_ctx(root))
    assert sig.files_over == 1


def test_custom_threshold(tmp_path):
    root = build_repo(tmp_path / "r", [
        {"subject": "feat (#1)", "files": {"a.py": _big(50), "b.py": _small()}},
    ])
    assert compute_size_signal(_ctx(root), threshold=40).files_over == 1
    assert compute_size_signal(_ctx(root), threshold=100).files_over == 0


def test_no_source_files_is_not_measurable(tmp_path):
    root = build_repo(tmp_path / "r", [
        {"subject": "docs (#1)", "files": {"README.md": "# hi\n", "data.json": "{}"}},
    ])
    sig = compute_size_signal(_ctx(root))
    assert sig.measurable is False
    assert sig.ratio is None
    assert sig.detail == "no source files to size"


def test_non_source_extensions_ignored(tmp_path):
    root = build_repo(tmp_path / "r", [
        {"subject": "feat (#1)",
         "files": {"a.py": _small(), "big.md": _big(), "big.txt": _big()}},
    ])
    sig = compute_size_signal(_ctx(root))
    # Only a.py counts; the oversize .md/.txt are not source.
    assert (sig.files_total, sig.files_over) == (1, 0)
