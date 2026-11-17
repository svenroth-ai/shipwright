"""L1: the publish guard of the release path — fixture notes never reach a real release page.

Split from ``test_release_seams.py`` to keep both files under the 300-line limit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

import release_seams as seams  # noqa: E402
from tools import create_github_release as cgr  # noqa: E402

@pytest.fixture(autouse=True)
def _no_seams(monkeypatch):
    for name in seams.SEAM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# --- the publish guard ---------------------------------------------------------------------

def _fixture_notes_file(tmp_path: Path) -> Path:
    notes = tmp_path / "notes.md"
    notes.write_text(seams.fixture_notes("1.2.3", "ok"), encoding="utf-8")
    return notes


@pytest.mark.covers("FR-01.09/AC14")
@pytest.mark.covers("FR-01.09/AC15")
def test_fixture_text_is_refused_unless_the_gh_seam_is_set(tmp_path: Path):
    with patch.object(cgr, "_run") as run:
        result = cgr.create_release("1.2.3", _fixture_notes_file(tmp_path), tmp_path)
    assert result == {"status": "failed",
                      "reason": f"fixture_notes_refused:{seams.GH_ARGV_PREFIX_ENV}_unset"}
    run.assert_not_called()  # refused before any gh call, not after a partial publish


@pytest.mark.covers("FR-01.09/AC14")
def test_fixture_text_is_published_when_the_gh_seam_is_set(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(seams.GH_ARGV_PREFIX_ENV, json.dumps(["py", "stub.py"]))

    def fake_run(args, *, timeout=30.0):
        if args[2:4] == ["release", "view"]:
            return _completed(1, stderr="release not found")
        if args[2:4] == ["release", "create"]:
            return _completed(0, stdout="https://stub/v1.2.3\n")
        return _completed(0, stdout="gh version 2.60.0 (x)")

    with patch.object(cgr, "_run", side_effect=fake_run), \
         patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"):
        result = cgr.create_release("1.2.3", _fixture_notes_file(tmp_path), tmp_path)
    assert result == {"status": "ok", "url": "https://stub/v1.2.3", "seam": "gh"}


@pytest.mark.covers("FR-01.09/AC14")
def test_plain_notes_are_not_affected_by_the_guard(tmp_path: Path):
    notes = tmp_path / "notes.md"
    notes.write_text("## Highlights\n\nreal notes\n", encoding="utf-8")
    assert cgr._fixture_notes_refusal(notes) is None
    assert cgr._fixture_notes_refusal(tmp_path / "missing.md") is None


@pytest.mark.covers("FR-01.09/AC14")
def test_a_real_stub_process_serves_the_whole_release_page_flow(tmp_path: Path, monkeypatch):
    """No mocks of ``_run``: the interpreter-plus-script prefix really spawns."""
    stub = tmp_path / "gh_stub.py"
    stub.write_text(
        "import sys\n"
        "a = sys.argv[1:]\n"
        "if a[:1] == ['--version']: print('gh version 2.60.0 (stub)')\n"
        "elif a[:1] == ['auth']: pass\n"
        "elif a[:2] == ['release', 'view']: sys.stderr.write('release not found'); sys.exit(1)\n"
        "elif a[:2] == ['release', 'create']: print('https://stub.invalid/' + a[2])\n"
        "else: sys.exit(2)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(seams.GH_ARGV_PREFIX_ENV, json.dumps([sys.executable, str(stub)]))
    with patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"):
        result = cgr.create_release("1.2.3", _fixture_notes_file(tmp_path), tmp_path)
    assert result == {"status": "ok", "url": "https://stub.invalid/v1.2.3", "seam": "gh"}


@pytest.mark.covers("FR-01.09/AC14")
@pytest.mark.covers("FR-01.09/AC15")
def test_an_unreadable_notes_file_keeps_the_default_behaviour(tmp_path: Path):
    """No fixture trigger: an unreadable notes file is left to the checks that always handled it."""
    assert cgr._fixture_notes_refusal(tmp_path) is None  # a directory: present, not readable as text


@pytest.mark.covers("FR-01.09/AC14")
@pytest.mark.covers("FR-01.09/AC15")
def test_a_seamed_result_says_so_and_a_default_result_does_not(tmp_path: Path, monkeypatch):
    with patch.object(cgr, "_gh_version", return_value=None):
        assert cgr.create_release("1.2.3", tmp_path / "n.md", tmp_path) == {
            "status": "skipped", "reason": "gh_not_found"}
        monkeypatch.setenv(seams.GH_ARGV_PREFIX_ENV, json.dumps(["py", "stub.py"]))
        assert cgr.create_release("1.2.3", tmp_path / "n.md", tmp_path)["seam"] == "gh"


@pytest.mark.covers("FR-01.09/AC14")
@pytest.mark.covers("FR-01.09/AC15")
def test_a_prefix_with_a_control_character_is_refused(monkeypatch):
    """An unescaped Windows path in JSON turns backslash-t into a tab: refuse, do not misread as no gh."""
    monkeypatch.setenv(seams.GH_ARGV_PREFIX_ENV, r'["C:\tools"]')
    with pytest.raises(seams.SeamError):
        seams.gh_command("--version")


@pytest.mark.covers("FR-01.09/AC14")
@pytest.mark.covers("FR-01.09/AC15")
@pytest.mark.parametrize("value", ["ok", "yes"])
def test_create_release_refuses_when_the_fixture_variable_is_set_without_the_gh_seam(
        tmp_path: Path, monkeypatch, value):
    """The guard's second trigger, through the public entry point: no marker in the notes."""
    monkeypatch.setenv(seams.CONDENSE_FIXTURE_ENV, value)
    notes = tmp_path / "notes.md"
    notes.write_text("## Highlights\n\nplain notes, no marker\n", encoding="utf-8")
    with patch.object(cgr, "_run") as run:
        result = cgr.create_release("1.2.3", notes, tmp_path)
    assert result == {"status": "failed",
                      "reason": f"fixture_notes_refused:{seams.GH_ARGV_PREFIX_ENV}_unset"}
    run.assert_not_called()
