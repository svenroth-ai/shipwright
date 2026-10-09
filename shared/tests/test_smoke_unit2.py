"""`scripts/_smoke_check.py` — throwaway smoke check for the PR #860 campaign.

Lives in `shared/tests/` rather than a repo-root `tests/`: the repo has no root
test directory, and the root `conftest.py` enforces one test root per pytest
process, so a new root would be an unregistered fifth root. The subject is
loaded by path, never via `sys.path` (ADR-045).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBJECT = _REPO_ROOT / "scripts" / "_smoke_check.py"


def _load_subject(name: str = "_smoke_check_probe"):
    spec = importlib.util.spec_from_file_location(name, _SUBJECT)
    assert spec is not None and spec.loader is not None, _SUBJECT
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # register BEFORE exec — ADR-045
    spec.loader.exec_module(module)
    return module


smoke = _load_subject()


def test_missing_file_fails(tmp_path: Path) -> None:
    ok, message = smoke.check(tmp_path)
    assert ok is False
    assert "missing" in message


def test_empty_file_fails(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "_smoke" / "unit-2.md"
    target.parent.mkdir(parents=True)
    target.write_text("  \n\t\n", encoding="utf-8")
    ok, message = smoke.check(tmp_path)
    assert ok is False
    assert "empty" in message


# Code points, never literals: an editor that drops an invisible literal would turn
# the input into plain whitespace and leave this test green while testing nothing.
_FORMAT_CHARS = [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x200E, 0x200F, 0x2061]


@pytest.mark.parametrize("code_point", _FORMAT_CHARS, ids=hex)
def test_format_chars_only_fails(tmp_path: Path, code_point: int) -> None:
    content = chr(code_point) * 2 + chr(10)
    assert content.strip(), "precondition: plain strip() must keep this character"
    target = tmp_path / "docs" / "_smoke" / "unit-2.md"
    target.parent.mkdir(parents=True)
    target.write_text(content, encoding="utf-8")
    ok, message = smoke.check(tmp_path)
    assert ok is False
    assert "empty" in message


def test_non_empty_file_passes(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "_smoke" / "unit-2.md"
    target.parent.mkdir(parents=True)
    target.write_text("smoke\n", encoding="utf-8")
    ok, _ = smoke.check(tmp_path)
    assert ok is True


def test_directory_at_target_path_fails(tmp_path: Path) -> None:
    (tmp_path / "docs" / "_smoke" / "unit-2.md").mkdir(parents=True)
    ok, message = smoke.check(tmp_path)
    assert ok is False
    assert "not a file" in message


def test_invalid_utf8_fails_cleanly(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "_smoke" / "unit-2.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xff\xfe\xfa not utf-8")
    ok, message = smoke.check(tmp_path)
    assert ok is False
    assert "unreadable" in message


def test_main_exit_codes_in_process(tmp_path: Path) -> None:
    assert smoke.main(["--project-root", str(tmp_path)]) == 1
    target = tmp_path / "docs" / "_smoke" / "unit-2.md"
    target.parent.mkdir(parents=True)
    target.write_text("smoke\n", encoding="utf-8")
    assert smoke.main(["--project-root", str(tmp_path)]) == 0


def test_real_repo_doc_passes_via_cli() -> None:
    """Round-trip: the committed doc, read by the script as a real process."""
    result = subprocess.run(
        [sys.executable, str(_SUBJECT), "--project-root", str(_REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_default_root_is_independent_of_cwd(tmp_path: Path) -> None:
    """No --project-root: the repo root comes from the script's location, not cwd."""
    result = subprocess.run(
        [sys.executable, str(_SUBJECT)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_exits_one_when_missing(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_SUBJECT), "--project-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
