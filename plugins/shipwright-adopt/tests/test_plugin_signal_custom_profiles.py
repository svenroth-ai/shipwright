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
    assert (before["matched"], before["source"]) == (name, "project")
    assert (after["matched"], after["source"]) == (name, "project")
    assert before["confidence"] == 1.0
    assert after["confidence"] == 1.0  # the score of a profile without the key is unchanged


def test_project_profile_with_more_dependencies_wins_and_keeps_its_score(tmp_path):
    plain = _repo(tmp_path / "plain", ("fastapi",), plugin=False)
    plugin = _repo(tmp_path / "plugin", ("fastapi",), plugin=True)
    for r in (plain, plugin):
        _profile(r, "my-api", ["python"], ["fastapi", "uvicorn"])
    a, b = analyze(plain, [], None)["profile"], analyze(plugin, [], None)["profile"]
    assert (a["matched"], a["source"]) == ("my-api", "project")
    assert (b["matched"], b["source"]) == ("my-api", "project")
    assert a["confidence"] == b["confidence"]


def test_bundled_profiles_not_declaring_the_key_keep_their_scores(tmp_path):
    plain = _repo(tmp_path / "plain", ("fastapi",), plugin=False)
    plugin = _repo(tmp_path / "plugin", ("fastapi",), plugin=True)
    def score(root):
        return {c["name"]: c["score"] for c in analyze(root, [], None)["profile"]["candidates"]}

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
    assert scores["claude-plugin"] == 1.0
    assert scores["python-plugin-monorepo"] == 1.0
    assert res["matched"] == "claude-plugin"

    # the same decision with names that sort the other way round
    pdir = tmp_path / "profiles"
    pdir.mkdir()
    for name, runtime in (("aaa-generic", {"python": "3"}), ("zzz-plugin", {"python": "3", "claude-plugin": "x"})):
        (pdir / f"{name}.json").write_text(json.dumps({"name": name, "stack": {"runtime": runtime}}), encoding="utf-8")
    sig = {"runtime": {"python": ">=3.11", "claude-plugin": ".claude-plugin/"}}
    assert match_profile(sig, pdir)["matched"] == "zzz-plugin"
    assert match_profile({"runtime": {"python": ">=3.11"}}, pdir)["matched"] == "aaa-generic"


def test_a_partly_matching_project_profile_keeps_winning_over_the_bundled_plugin_profile(tmp_path):
    """requires-python + fastapi; project profile declares two undetectable extras: it scored 0.5 and tied the bundled one."""
    plain = _repo(tmp_path / "plain", ("fastapi",), plugin=False)
    plugin = _repo(tmp_path / "plugin", ("fastapi",), plugin=True)
    for r in (plain, plugin):
        _profile(r, "my-api", ["python"], ["fastapi", "uvicorn", "pydantic"])
    a, b = analyze(plain, [], None)["profile"], analyze(plugin, [], None)["profile"]
    assert (a["matched"], a["source"], a["confidence"]) == ("my-api", "project", 0.5)
    assert (b["matched"], b["source"], b["confidence"]) == ("my-api", "project", 0.5)


def test_a_python_repo_without_the_folder_is_not_offered_the_plugin_profile(tmp_path):
    """The plugin profile is a candidate only where the signature carries its key (candidates feed the adopt interview)."""
    plain = _repo(tmp_path / "plain", ("fastapi",), plugin=False)
    assert "claude-plugin" not in {c["name"] for c in analyze(plain, [], None)["profile"]["candidates"]}


def test_the_facts_the_no_match_moves_proof_rests_on():
    """claude-plugin declares exactly the generic profile's names plus the signal; no other bundled profile ties it on Python signatures."""
    from lib.profile_matcher import SIGNAL_KEYS, match_profile

    root = Path(__file__).resolve().parents[3] / "shared" / "profiles"

    def deps(name):
        stack = json.loads((root / f"{name}.json").read_text(encoding="utf-8"))["stack"]
        return {k for group in ("runtime", "frontend", "backend") for k in stack.get(group, {}) if not k.startswith("_")}

    assert deps("claude-plugin") - SIGNAL_KEYS == deps("python-plugin-monorepo")
    for sig in ({"runtime": {"python": ">=3.11"}}, {"runtime": {"python": ">=3.11"}, "backend": {"fastapi": "x"}, "database": {"psycopg": "x"}}):
        scores = {c["name"]: c["score"] for c in match_profile(sig, root)["candidates"]}
        generic = scores["python-plugin-monorepo"]
        for other in ("chat-first-json", "skill-companion-app"):
            assert scores.get(other, 0.0) < generic, (other, scores)
