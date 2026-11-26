"""P8b fix round 2, end to end on real git: an entry that reaches column 0 stays in ``[Unreleased]``, so the readers of the
release section (``release_pr_body.section_text`` and ``extract_changelog_section.py``, both bounded by the shared
``changelog_sections.section_end``) see every moved entry and every later category."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib import release_pr_body

from .test_release_event_real_git import git

pytestmark = pytest.mark.covers("FR-01.09/AC09")
TOOLS = Path(__file__).resolve().parents[3] / "shared" / "scripts" / "tools"
FENCE = "`" * 3
LAZY = "- Lazy entry\nwrapped at column 0\n"
FENCED = f"- Fence entry\n{FENCE}\ncode at column 0\n{FENCE}\n"
CHANGELOG = ("# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Normal added entry\n  indented continuation\n" + LAZY + FENCED
             + "\n### Fixed\n\n- Later category fix\n\n## [1.2.0] - 2026-01-15\n\n- Old\n")


def _tool(root: Path, name: str, *args: str) -> dict:
    done = subprocess.run([sys.executable, str(TOOLS / name), "--project-root", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout)


def test_column_0_entries_stay_named_and_both_readers_see_every_moved_entry_and_later_category(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n",
                      encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "work"
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "CHANGELOG.md").write_bytes(CHANGELOG.encode("utf-8"))
    out = _tool(root, "aggregate_changelog.py", "--version", "1.3.0", "--release-date", "2026-11-26", "--move-unreleased")
    assert out["legacy_unreleased_bullet_texts"] == ["Lazy entry", "Fence entry"]  # named in the warning
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased, released = text.split("## [1.3.0]")
    assert LAZY + FENCED in unreleased  # each stayed whole
    git(root, "add", "CHANGELOG.md")
    git(root, "commit", "-q", "-m", "release")
    git(root, "tag", "-a", "v1.3.0", "-m", "v1.3.0")
    pr_section, count = release_pr_body.section_text(text, "1.3.0")
    extracted = _tool(root, "extract_changelog_section.py", "--version", "1.3.0")["section_text"]
    for section in (pr_section, extracted):
        assert "- Normal added entry\n  indented continuation" in section
        assert "### Fixed\n\n- Later category fix" in section
        assert "Lazy entry" not in section and "Fence entry" not in section
    assert count == 1
