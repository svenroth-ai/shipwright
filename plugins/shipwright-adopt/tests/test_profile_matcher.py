"""Unit tests for profile_matcher.match_profile."""

from pathlib import Path

import pytest

from lib.plugin_signal import add_plugin_signal
from lib.profile_matcher import match_profile
from lib.stack_detector import detect_stack


def _profiles_dir() -> Path:
    # Walk up from tests/ to repo root and then to shared/profiles/
    # plugins/shipwright-adopt/tests -> plugins/shipwright-adopt -> plugins -> repo root
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent.parent
    return repo_root / "shared" / "profiles"


def test_supabase_nextjs_matched(nextjs_repo: Path) -> None:
    sig = detect_stack(nextjs_repo)
    result = match_profile(sig, _profiles_dir())
    assert result["matched"] == "supabase-nextjs"
    assert result["confidence"] > 0.3


def test_python_matches_plugin_monorepo(python_cli: Path) -> None:
    sig = detect_stack(python_cli)
    result = match_profile(sig, _profiles_dir())
    # Since the 2026-05-02 self-adoption shipped
    # shared/profiles/python-plugin-monorepo.json, a python-only signature
    # now matches that profile (Jaccard score 1.0) instead of falling back
    # to generic. The old assertion was correct for the world with no python
    # profile in shared/profiles/; updated to reflect current behavior.
    assert result["matched"] == "python-plugin-monorepo"
    assert result["confidence"] >= 0.30


def test_missing_profiles_dir(tmp_path: Path) -> None:
    sig = {"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}}
    result = match_profile(sig, tmp_path / "nonexistent")
    assert result["matched"] == "generic"
    assert result["confidence"] == 0.0


def _python_repo(tmp_path: Path, python_cli: Path) -> Path:
    import shutil

    root = tmp_path / "repo"
    shutil.copytree(python_cli, root)
    return root


@pytest.mark.covers("FR-01.01/AC31")
def test_plugin_repo_matches_claude_plugin(tmp_path: Path, python_cli: Path) -> None:
    root = _python_repo(tmp_path, python_cli)
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    sig = add_plugin_signal(detect_stack(root), root)
    assert "has-claude-plugin-dir" in sig["signals"]
    result = match_profile(sig, _profiles_dir())
    assert result["matched"] == "claude-plugin"
    scores = {c["name"]: c["score"] for c in result["candidates"]}
    assert scores["claude-plugin"] > scores["python-plugin-monorepo"]


@pytest.mark.covers("FR-01.01/AC31")
def test_plugin_monorepo_layout_matches_claude_plugin(tmp_path: Path, python_cli: Path) -> None:
    root = _python_repo(tmp_path, python_cli)
    (root / "plugins" / "demo" / ".claude-plugin").mkdir(parents=True)
    assert match_profile(add_plugin_signal(detect_stack(root), root), _profiles_dir())["matched"] == "claude-plugin"


@pytest.mark.covers("FR-01.01/AC31")
def test_python_only_repo_without_the_folder_keeps_the_generic_profile(tmp_path: Path, python_cli: Path) -> None:
    root = _python_repo(tmp_path, python_cli)
    (root / "plugins" / "demo").mkdir(parents=True)  # a plugins/ folder alone is not the signal
    sig = add_plugin_signal(detect_stack(root), root)
    assert "has-claude-plugin-dir" not in sig["signals"] and "claude-plugin" not in sig["runtime"]
    result = match_profile(sig, _profiles_dir())
    assert result["matched"] == "python-plugin-monorepo"
    scores = {c["name"]: c["score"] for c in result["candidates"]}
    assert scores["python-plugin-monorepo"] > scores.get("claude-plugin", 0.0)


@pytest.mark.covers("FR-01.01/AC31")
def test_signal_needs_a_folder_at_the_two_supported_depths(tmp_path: Path, python_cli: Path) -> None:
    root = _python_repo(tmp_path, python_cli)
    (root / ".claude-plugin").write_text("not a folder", encoding="utf-8")  # a file of that name
    (root / "plugins" / "demo" / "deeper" / ".claude-plugin").mkdir(parents=True)  # one level too deep
    (root / "docs" / ".claude-plugin").mkdir(parents=True)  # not under plugins/
    sig = add_plugin_signal(detect_stack(root), root)
    assert "claude-plugin" not in sig["runtime"] and match_profile(sig, _profiles_dir())["matched"] == "python-plugin-monorepo"


@pytest.mark.covers("FR-01.01/AC31")
def test_signal_key_is_not_a_spec_constraint_and_python_version_survives(tmp_path: Path, python_cli: Path) -> None:
    from tools.generate_adoption_artifacts import _extract_constraints

    root = _python_repo(tmp_path, python_cli)
    (root / ".claude-plugin").mkdir()
    sig = add_plugin_signal(detect_stack(root), root)
    constraints = _extract_constraints({"stack": sig})
    assert constraints == ["Python version: >=3.11"]


@pytest.mark.covers("FR-01.01/AC31")
def test_analysis_snapshot_gives_each_repo_its_profile(tmp_path: Path, python_cli: Path, monkeypatch) -> None:
    """The whole analysis (what /shipwright-adopt runs), not only the matcher: plugin repo vs plain Python CLI."""
    from tools.analyze_codebase import analyze

    for var in ("HOME", "USERPROFILE"):  # no user profiles of the machine in the discovery
        monkeypatch.setenv(var, str(tmp_path / "home"))

    plain = _python_repo(tmp_path / "plain", python_cli)
    plugin = _python_repo(tmp_path / "plugin", python_cli)
    (plugin / ".claude-plugin").mkdir()
    assert analyze(plain, [], None)["profile"]["matched"] == "python-plugin-monorepo"
    assert analyze(plugin, [], None)["profile"]["matched"] == "claude-plugin"


def test_adding_the_signal_twice_changes_nothing(tmp_path: Path, python_cli: Path) -> None:
    root = _python_repo(tmp_path, python_cli)
    (root / ".claude-plugin").mkdir()
    once = add_plugin_signal(detect_stack(root), root)
    assert add_plugin_signal(once, root)["signals"].count("has-claude-plugin-dir") == 1
