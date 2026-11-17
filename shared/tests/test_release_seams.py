"""L1: the ``SHIPWRIGHT_TEST_*`` seams of the release path (``release_seams.py``).

Per seam: inert when unset (the default path is unchanged), read in one place,
documented, and guarded so fixture notes can never be published for real.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

import release_seams as seams  # noqa: E402
from tools import condense_release_notes as crn  # noqa: E402
from tools import create_github_release as cgr  # noqa: E402
from tools import validate_release_notes as vrn  # noqa: E402

_DOC = _REPO_ROOT / "docs" / "hooks-and-pipeline.md"


@pytest.fixture(autouse=True)
def _no_seams(monkeypatch):
    for name in seams.SEAM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# --- the registry: named, documented, read in one place ------------------------------------

@pytest.mark.covers("FR-01.09/AC14")
def test_every_seam_is_named_shipwright_test():
    assert seams.SEAM_ENV_VARS
    assert all(re.fullmatch(r"SHIPWRIGHT_TEST_[A-Z0-9_]+", name) for name in seams.SEAM_ENV_VARS)


@pytest.mark.covers("FR-01.09/AC14")
def test_every_seam_is_documented():
    doc = _DOC.read_text(encoding="utf-8")
    assert [name for name in seams.SEAM_ENV_VARS if name not in doc] == []


@pytest.mark.covers("FR-01.09/AC14")
def test_seams_are_read_in_one_place():
    """No release-path script outside ``release_seams.py`` names a seam variable."""
    scripts = [*(_REPO_ROOT / "shared" / "scripts").rglob("*.py"),
               *(_REPO_ROOT / "plugins" / "shipwright-changelog" / "scripts").rglob("*.py")]
    offenders = [
        str(path.relative_to(_REPO_ROOT)) for path in scripts
        if path.name != "release_seams.py" and "tests" not in path.parts
        and any(name in path.read_text(encoding="utf-8") for name in seams.SEAM_ENV_VARS)
    ]
    assert offenders == []


# --- gh argv prefix ------------------------------------------------------------------------

@pytest.mark.covers("FR-01.09/AC14")
def test_gh_command_default_is_plain_gh():
    assert seams.gh_command("release", "view", "v1.0.0") == ["gh", "release", "view", "v1.0.0"]
    assert seams.gh_seam_active() is False


@pytest.mark.covers("FR-01.09/AC14")
def test_empty_value_is_inert(monkeypatch):
    monkeypatch.setenv(seams.GH_ARGV_PREFIX_ENV, "")
    assert seams.gh_command("--version") == ["gh", "--version"]
    assert seams.gh_seam_active() is False


@pytest.mark.covers("FR-01.09/AC14")
def test_gh_prefix_replaces_the_leading_gh(monkeypatch):
    monkeypatch.setenv(seams.GH_ARGV_PREFIX_ENV, json.dumps([sys.executable, "stub.py"]))
    assert seams.gh_command("auth", "status") == [sys.executable, "stub.py", "auth", "status"]
    assert seams.gh_seam_active() is True


@pytest.mark.covers("FR-01.09/AC14")
@pytest.mark.covers("FR-01.09/AC15")
@pytest.mark.parametrize("raw", ["not json", "{}", "[]", '["ok", 3]', '[""]', '"gh"',
                                 '["gh"]', '["C:\\tools\\gh.exe", "x"]', '["/usr/bin/gh"]'])
def test_malformed_gh_prefix_is_refused_not_ignored(monkeypatch, raw):
    monkeypatch.setenv(seams.GH_ARGV_PREFIX_ENV, raw)
    with pytest.raises(seams.SeamError):
        seams.gh_command("--version")


@pytest.mark.covers("FR-01.09/AC14")
def test_create_release_default_argv_is_unchanged(tmp_path: Path):
    notes = tmp_path / "notes.md"
    notes.write_text("## Highlights\n\nplain notes for 1.2.3\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(args, *, timeout=30.0):
        calls.append(list(args))
        if args[1:3] == ["release", "view"]:
            return _completed(1, stderr="release not found")
        if args[1:3] == ["release", "create"]:
            return _completed(0, stdout="https://github.com/acme/widgets/releases/tag/v1.2.3\n")
        return _completed(0, stdout="gh version 2.60.0 (x)")

    with patch.object(cgr, "_run", side_effect=fake_run), \
         patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"):
        result = cgr.create_release("1.2.3", notes, tmp_path)

    assert result["status"] == "ok"
    assert calls == [
        ["gh", "--version"],
        ["gh", "auth", "status", "--hostname", "github.com"],
        ["gh", "release", "view", "v1.2.3", "--repo", "acme/widgets", "--json", "url"],
        ["gh", "release", "create", "v1.2.3", "--notes-file", str(notes), "--title", "v1.2.3",
         "--verify-tag", "--repo", "acme/widgets"],
    ]


@pytest.mark.covers("FR-01.09/AC14")
def test_create_release_uses_the_seam_prefix_on_every_call(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(seams.GH_ARGV_PREFIX_ENV, json.dumps(["py", "stub.py"]))
    notes = tmp_path / "notes.md"
    notes.write_text("plain notes\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(args, *, timeout=30.0):
        calls.append(list(args))
        if args[2:4] == ["release", "view"]:
            return _completed(0, stdout='{"url": "https://x"}')
        return _completed(0, stdout="gh version 2.60.0 (x)")

    with patch.object(cgr, "_run", side_effect=fake_run), \
         patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"):
        assert cgr.create_release("1.2.3", notes, tmp_path)["status"] == "exists"

    assert calls and all(call[:2] == ["py", "stub.py"] for call in calls)


@pytest.mark.covers("FR-01.09/AC14")
@pytest.mark.covers("FR-01.09/AC15")
def test_create_release_reports_a_malformed_seam_without_calling_gh(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(seams.GH_ARGV_PREFIX_ENV, "not json")
    with patch.object(cgr, "_run") as run:
        result = cgr.create_release("1.2.3", tmp_path / "notes.md", tmp_path)
    assert result["status"] == "failed" and result["reason"].startswith("seam_invalid:")
    run.assert_not_called()


# --- condensation fixture model ------------------------------------------------------------

@pytest.mark.covers("FR-01.09/AC14")
def test_condense_default_still_needs_a_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert seams.condense_fixture_mode() is None
    assert crn.condense("s", "1.2.3", "p", project_root=tmp_path) == {
        "status": "skipped", "reason": "no_api_key"}


@pytest.mark.covers("FR-01.09/AC14")
def test_condense_default_still_calls_the_provider_when_a_key_is_set(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch.object(crn, "_call_openrouter", return_value={"status": "ok", "text": "t", "via": "openrouter"}) as call:
        result = crn.condense("s", "1.2.3", "p", project_root=tmp_path)
    call.assert_called_once()
    assert result["via"] == "openrouter"


@pytest.mark.covers("FR-01.09/AC14")
def test_fixture_model_needs_no_key_and_never_reaches_a_provider(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv(seams.CONDENSE_FIXTURE_ENV, "ok")
    with patch.object(crn, "_call_openrouter") as provider:
        result = crn.condense("s", "1.2.3", "p", project_root=tmp_path)
    provider.assert_not_called()
    assert result == {"status": "ok", "text": seams.fixture_notes("1.2.3", "ok"), "via": "fixture"}


@pytest.mark.covers("FR-01.09/AC14")
def test_fixture_model_wins_over_a_real_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv(seams.CONDENSE_FIXTURE_ENV, "ok")
    with patch.object(crn, "_call_openrouter") as provider:
        assert crn.condense("s", "1.2.3", "p", project_root=tmp_path)["via"] == "fixture"
    provider.assert_not_called()


@pytest.mark.covers("FR-01.09/AC14")
def test_unknown_fixture_mode_is_an_error_not_a_provider_call(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv(seams.CONDENSE_FIXTURE_ENV, "yes")
    with patch.object(crn, "_call_openrouter") as provider:
        result = crn.condense("s", "1.2.3", "p", project_root=tmp_path)
    assert result["status"] == "error" and result["reason"].startswith("seam_invalid:")
    provider.assert_not_called()


def _validate(text: str):
    footer = vrn.expected_footer("1.2.3", "https://github.com/acme/widgets/blob/v1.2.3/CHANGELOG.md", None)
    return vrn.validate(text, "1.2.3", footer=footer, repo_identity="acme/widgets")


@pytest.mark.covers("FR-01.09/AC14")
def test_ok_fixture_passes_the_shape_check_and_keeps_its_marker():
    result = _validate(seams.fixture_notes("1.2.3", "ok"))
    assert result.ok, result.reason
    assert seams.FIXTURE_MARKER in result.sanitized_body


@pytest.mark.covers("FR-01.09/AC14")
@pytest.mark.covers("FR-01.09/AC15")
def test_bad_shape_fixture_fails_the_shape_check():
    assert _validate(seams.fixture_notes("1.2.3", "bad-shape")).ok is False


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
