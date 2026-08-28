"""Tests for `extract_changelog_section.py` — reads the TAGGED CHANGELOG.md
blob (never the worktree), slices the version section via the shared
`changelog_sections` SSoT, and resolves a semver+remote-verified previous
version for the release body's compare link.

Uses a real local git repo with a local bare "origin" (no network) so the
`git show` / `git tag` / `git ls-remote` calls are genuine, not mocked —
this is what makes the aggregator<->extractor round-trip probe meaningful.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

sys.path.append(str(Path(__file__).resolve().parent))
from _changelog_release_fixtures import HEADER  # noqa: E402

from tools import extract_changelog_section as ecs  # noqa: E402
from tools.aggregate_changelog import _render_versioned_section  # noqa: E402


def _init_repo_with_origin(tmp_path: Path) -> tuple[Path, Path]:
    """Returns (working_repo, bare_origin) — a local bare repo standing in
    for `origin`, so `git ls-remote --tags origin` is real but network-free."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    subprocess.run(["git", "init", "-q", "--bare"], cwd=origin, check=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=repo, check=True)
    return repo, origin


def _commit_changelog_and_tag(repo: Path, changelog_text: str, tag: str, *, push: bool = True) -> None:
    (repo / "CHANGELOG.md").write_text(changelog_text, encoding="utf-8")
    subprocess.run(["git", "add", "CHANGELOG.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"chore: {tag}"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], cwd=repo, check=True)
    if push:
        # Push HEAD + only THIS tag — `--tags` pushes every local tag,
        # which would defeat the "tag never pushed" test scenario below.
        subprocess.run(["git", "push", "-q", "origin", "HEAD", tag], cwd=repo, check=True)


def test_extract_section_present(tmp_path: Path):
    repo, _origin = _init_repo_with_origin(tmp_path)
    changelog = HEADER + "## [1.0.0] - 2026-01-01\n\n### Added\n\n- first\n"
    _commit_changelog_and_tag(repo, changelog, "v1.0.0")

    result = ecs.extract(repo, "1.0.0")
    assert result["status"] == "ok"
    assert "### Added" in result["section_text"]
    assert "- first" in result["section_text"]
    assert result["previous_version_tag"] is None  # first-ever release


def test_extract_section_absent_raises(tmp_path: Path):
    """The tag exists (Step 7 only ever runs against a version it just
    tagged) but the tagged CHANGELOG.md has no heading for it — e.g. the
    aggregator step was skipped or failed silently upstream."""
    repo, _origin = _init_repo_with_origin(tmp_path)
    changelog = HEADER + "## [1.0.0] - 2026-01-01\n\n### Added\n\n- first\n"
    _commit_changelog_and_tag(repo, changelog, "v2.0.0")

    with pytest.raises(ecs.ExtractError, match=r"no '## \[2\.0\.0\]'"):
        ecs.extract(repo, "2.0.0")


def test_extract_section_ambiguous_raises(tmp_path: Path):
    repo, _origin = _init_repo_with_origin(tmp_path)
    changelog = (
        HEADER
        + "## [1.0.0] - 2026-01-01\n\n### Added\n\n- a\n\n"
        + "## [1.0.0] - 2026-01-02\n\n### Added\n\n- b\n"
    )
    _commit_changelog_and_tag(repo, changelog, "v1.0.0")

    with pytest.raises(ecs.ExtractError, match="ambiguous"):
        ecs.extract(repo, "1.0.0")


def test_extract_missing_tag_raises(tmp_path: Path):
    repo, _origin = _init_repo_with_origin(tmp_path)
    with pytest.raises(ecs.ExtractError, match="is it pushed"):
        ecs.extract(repo, "9.9.9")


def test_extract_previous_version_semver_ordering(tmp_path: Path):
    """v0.10.0 must sort after v0.9.0 — a string comparison would get this
    backwards (Round 2, deepseek finding)."""
    repo, _origin = _init_repo_with_origin(tmp_path)
    _commit_changelog_and_tag(repo, HEADER + "## [0.9.0] - 2026-01-01\n\n### Added\n\n- a\n", "v0.9.0")
    _commit_changelog_and_tag(
        repo,
        HEADER + "## [0.9.0] - 2026-01-01\n\n### Added\n\n- a\n\n"
        "## [0.10.0] - 2026-01-05\n\n### Added\n\n- b\n",
        "v0.10.0",
    )
    result = ecs.extract(repo, "0.10.0")
    assert result["previous_version_tag"] == "v0.9.0"


def test_extract_previous_tag_not_on_remote_is_omitted(tmp_path: Path):
    """A local-only tag (never pushed) must not produce a compare link that
    would 404 (Round 2, openai finding)."""
    repo, _origin = _init_repo_with_origin(tmp_path)
    _commit_changelog_and_tag(
        repo, HEADER + "## [0.9.0] - 2026-01-01\n\n### Added\n\n- a\n", "v0.9.0", push=False
    )
    _commit_changelog_and_tag(
        repo,
        HEADER + "## [0.9.0] - 2026-01-01\n\n### Added\n\n- a\n\n"
        "## [1.0.0] - 2026-01-05\n\n### Added\n\n- b\n",
        "v1.0.0",
    )
    result = ecs.extract(repo, "1.0.0")
    assert result["previous_version_tag"] is None


def test_extract_ignores_non_semver_tag_noise(tmp_path: Path):
    repo, _origin = _init_repo_with_origin(tmp_path)
    subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", "init"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "v-next"], cwd=repo, check=True)
    _commit_changelog_and_tag(repo, HEADER + "## [1.0.0] - 2026-01-01\n\n### Added\n\n- a\n", "v1.0.0")
    result = ecs.extract(repo, "1.0.0")
    assert result["previous_version_tag"] is None


def test_extract_oversized_section_refused(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ecs, "MAX_SECTION_BYTES", 32)
    repo, _origin = _init_repo_with_origin(tmp_path)
    changelog = HEADER + "## [1.0.0] - 2026-01-01\n\n### Added\n\n- " + ("x" * 200) + "\n"
    _commit_changelog_and_tag(repo, changelog, "v1.0.0")
    with pytest.raises(ecs.ExtractError, match="exceeds"):
        ecs.extract(repo, "1.0.0")


def test_extract_succeeds_when_whole_file_exceeds_the_section_cap(tmp_path: Path, monkeypatch):
    """Regression guard: the size bound applies only to the SLICED section,
    never the whole tagged file — a mature CHANGELOG.md (this repo's own is
    450KB+) must not permanently refuse every future release just because
    its total size exceeds the cap (external code review finding)."""
    monkeypatch.setattr(ecs, "MAX_SECTION_BYTES", 200)
    repo, _origin = _init_repo_with_origin(tmp_path)
    padding = "## [0.1.0] - 2025-01-01\n\n### Added\n\n- " + ("x" * 500) + "\n\n"
    changelog = HEADER + padding + "## [1.0.0] - 2026-01-01\n\n### Added\n\n- small\n"
    assert len(changelog.encode("utf-8")) > 200
    _commit_changelog_and_tag(repo, changelog, "v1.0.0")

    result = ecs.extract(repo, "1.0.0")
    assert result["status"] == "ok"
    assert "- small" in result["section_text"]


def test_git_helper_raises_when_subprocess_itself_fails(tmp_path: Path):
    """`_git`'s OSError/TimeoutExpired branch — `git` not on PATH, or hangs."""
    with patch("tools.extract_changelog_section.subprocess.run", side_effect=OSError("git not found")):
        with pytest.raises(ecs.ExtractError, match="failed to run"):
            ecs._git(["status"], tmp_path)


def test_git_helper_survives_a_non_utf8_stdout_byte(tmp_path: Path):
    """Windows repro: without an explicit ``encoding=``, ``text=True``
    decodes via the locale's codec (cp1252 on Windows). A byte a changelog
    can genuinely contain (e.g. an em-dash mis-encoded upstream) crashes
    that decode inside subprocess's reader thread, leaving ``stdout`` as
    ``None`` — which then raised ``AttributeError`` on ``.splitlines()`` in
    ``_extract_section``. ``encoding="utf-8", errors="replace"`` must
    survive it instead."""
    real_run = subprocess.run

    def _non_utf8_child(*_args, **kwargs):
        return real_run(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\x8f')"],
            **kwargs,
        )

    with patch("tools.extract_changelog_section.subprocess.run", side_effect=_non_utf8_child):
        output = ecs._git(["status"], tmp_path)
    assert output is not None
    assert "�" in output


def test_remote_has_tag_false_when_git_command_itself_fails(tmp_path: Path):
    """A repo with no `origin` remote configured makes `git ls-remote --tags
    origin ...` fail for real (not mocked) — `_remote_has_tag` must treat
    that failure as `False`, not raise, since it's a probe, not a gate."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert ecs._remote_has_tag(tmp_path, "v1.0.0") is False


def test_main_prints_error_json_and_exits_1_when_extraction_fails(tmp_path: Path, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    rc = ecs.main(["--project-root", str(tmp_path), "--version", "9.9.9"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"


def test_main_prints_ok_json_on_success(tmp_path: Path, capsys):
    repo, _origin = _init_repo_with_origin(tmp_path)
    changelog = HEADER + "## [1.0.0] - 2026-01-01\n\n### Added\n\n- first\n"
    _commit_changelog_and_tag(repo, changelog, "v1.0.0")

    rc = ecs.main(["--project-root", str(repo), "--version", "1.0.0"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert "- first" in payload["section_text"]


def test_aggregator_extractor_round_trip(tmp_path: Path):
    """Byte-equality round-trip probe (Round 2, Boundary Probe finding):
    render a section exactly as the real aggregator does, commit+tag it,
    and assert the extractor returns the identical text back."""
    repo, _origin = _init_repo_with_origin(tmp_path)
    by_category = {
        "Added": [("stem1", "first bullet"), ("stem2", "second bullet")],
        "Fixed": [("stem3", "a fix")],
    }
    rendered_section = _render_versioned_section("2.0.0", "2026-06-01", by_category)
    changelog = HEADER + rendered_section
    _commit_changelog_and_tag(repo, changelog, "v2.0.0")

    result = ecs.extract(repo, "2.0.0")
    assert result["section_text"] == rendered_section
