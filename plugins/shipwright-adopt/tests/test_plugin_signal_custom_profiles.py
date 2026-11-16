"""The plugin signal never moves the match of a project's own profile (FR-01.01 AC31)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.analyze_codebase import analyze

pytestmark = pytest.mark.covers("FR-01.01/AC31")


def _repo(root: Path, deps: tuple[str, ...], plugin: bool) -> Path:
    root.mkdir(parents=True)
    body = ["[project]", 'name = "p"', 'requires-python = ">=3.11"']
    if deps:
        body.append("dependencies = [" + ", ".join(f'"{d}"' for d in deps) + "]")
    (root / "pyproject.toml").write_text(chr(10).join(body) + chr(10), encoding="utf-8")
    if plugin:
        (root / ".claude-plugin").mkdir()
    return root


def _profile(root: Path, name: str, runtime: list[str], backend: list[str] | None = None) -> None:
    path = root / ".shipwright" / "profiles" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    stack = {"runtime": {k: "1" for k in runtime}, "backend": {k: "1" for k in backend or []}}
    path.write_text(json.dumps({"name": name, "stack": stack}), encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_user_profiles(tmp_path, monkeypatch):
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(tmp_path / "home"))


@pytest.mark.parametrize("name", ["my-python", "python-plugin-monorepo"])  # own name, and a project copy shadowing the bundled name
def test_project_profile_with_only_python_still_wins_a_plugin_repo(tmp_path, name):
    root = _repo(tmp_path / "plain", (), plugin=False)
    plugin = _repo(tmp_path / "plugin", (), plugin=True)
    for r in (root, plugin):
        _profile(r, name, ["python"])
    before, after = analyze(root, [], None)["profile"], analyze(plugin, [], None)["profile"]
    assert (before["matched"], before["source"]) == (after["matched"], after["source"]) == (name, "project")
    assert before["confidence"] == after["confidence"] == 1.0  # the score of a profile without the key is unchanged


def test_project_profile_with_more_dependencies_wins_and_keeps_its_score(tmp_path):
    plain = _repo(tmp_path / "plain", ("fastapi",), plugin=False)
    plugin = _repo(tmp_path / "plugin", ("fastapi",), plugin=True)
    for r in (plain, plugin):
        _profile(r, "my-api", ["python"], ["fastapi", "uvicorn"])
    a, b = analyze(plain, [], None)["profile"], analyze(plugin, [], None)["profile"]
    assert (a["matched"], a["source"]) == (b["matched"], b["source"]) == ("my-api", "project")
    assert a["confidence"] == b["confidence"]


def test_bundled_profiles_not_declaring_the_key_keep_their_scores(tmp_path):
    plain = _repo(tmp_path / "plain", ("fastapi",), plugin=False)
    plugin = _repo(tmp_path / "plugin", ("fastapi",), plugin=True)
    score = lambda root: {c["name"]: c["score"] for c in analyze(root, [], None)["profile"]["candidates"]}  # noqa: E731
    assert score(plain)["python-plugin-monorepo"] == score(plugin)["python-plugin-monorepo"]


def test_the_signal_key_is_not_listed_as_a_runtime():
    from lib.render_helpers import _fmt_stack_line

    assert _fmt_stack_line({"python": ">=3.11", "claude-plugin": ".claude-plugin/"}) == "python"
    assert _fmt_stack_line({"claude-plugin": ".claude-plugin/"}) == "—"


def test_a_plain_plugin_repo_wins_the_tie_by_its_signal_not_by_name_order(tmp_path):
    """requires-python and no hinted dependencies: both bundled profiles score 1.0."""
    from lib.profile_matcher import match_profile

    root = _repo(tmp_path / "plugin", (), plugin=True)
    res = analyze(root, [], None)["profile"]
    scores = {c["name"]: c["score"] for c in res["candidates"]}
    assert scores["claude-plugin"] == scores["python-plugin-monorepo"] == 1.0 and res["matched"] == "claude-plugin"

    # the same decision with names that sort the other way round
    pdir = tmp_path / "profiles"
    pdir.mkdir()
    for name, runtime in (("aaa-generic", {"python": "3"}), ("zzz-plugin", {"python": "3", "claude-plugin": "x"})):
        (pdir / f"{name}.json").write_text(json.dumps({"name": name, "stack": {"runtime": runtime}}), encoding="utf-8")
    sig = {"runtime": {"python": ">=3.11", "claude-plugin": ".claude-plugin/"}}
    assert match_profile(sig, pdir)["matched"] == "zzz-plugin"
    assert match_profile({"runtime": {"python": ">=3.11"}}, pdir)["matched"] == "aaa-generic"
