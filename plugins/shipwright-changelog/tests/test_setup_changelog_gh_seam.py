"""L1: the ``gh`` argv-prefix seam in ``setup-changelog.py``'s previous-release check.

Unset, the check spawns exactly ``["gh", ...]`` as before; set, every ``gh`` call
of the check starts with the prefix; malformed, the advisory check reads as
indeterminate and never reaches a real ``gh``.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "checks" / "setup-changelog.py"
_spec = importlib.util.spec_from_file_location("setup_changelog_gh_seam", _SCRIPT_PATH)
setup_changelog = importlib.util.module_from_spec(_spec)
sys.modules["setup_changelog_gh_seam"] = setup_changelog
_spec.loader.exec_module(setup_changelog)  # noqa: E402

_SEAM = "SHIPWRIGHT_TEST_GH_ARGV_PREFIX"


@pytest.fixture(autouse=True)
def _no_seam(monkeypatch):
    monkeypatch.delenv(_SEAM, raising=False)


def _completed(returncode: int, stderr: str = "", stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _argvs(tmp_path: Path) -> tuple[bool | None, list[list[str]]]:
    seen: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        seen.append(list(argv))
        return _completed(0)

    with patch("setup_changelog_gh_seam.subprocess.run", side_effect=fake_run), \
         patch("setup_changelog_gh_seam.resolve_repo_identity", return_value="acme/widgets"):
        return setup_changelog._check_previous_release(tmp_path, "v1.0.0"), seen


@pytest.mark.covers("FR-01.09/AC14")
def test_default_spawns_plain_gh(tmp_path: Path):
    found, seen = _argvs(tmp_path)
    assert found is True
    assert seen == [
        ["gh", "--version"],
        ["gh", "release", "view", "v1.0.0", "--repo", "acme/widgets", "--json", "url"],
    ]


@pytest.mark.covers("FR-01.09/AC14")
def test_seam_prefix_leads_every_gh_call(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(_SEAM, json.dumps(["py", "stub.py"]))
    found, seen = _argvs(tmp_path)
    assert found is True
    assert seen == [
        ["py", "stub.py", "--version"],
        ["py", "stub.py", "release", "view", "v1.0.0", "--repo", "acme/widgets", "--json", "url"],
    ]


@pytest.mark.covers("FR-01.09/AC14")
@pytest.mark.covers("FR-01.09/AC15")
def test_malformed_seam_is_indeterminate_says_so_and_spawns_nothing(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv(_SEAM, "not json")
    found, seen = _argvs(tmp_path)
    assert found is None
    assert seen == []
    assert "seam_invalid" in capsys.readouterr().err
