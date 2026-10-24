"""End to end: custom stack profiles through every command loader (campaign stack-profile-resolver S5).

A tmp project is built at runtime and run from a **git worktree** of it (no committed fixtures): a
project profile is only useful if a fresh checkout sees it, which is what D10 (the gitignore
exception) is for. Each scenario drives the real command-line entry points as subprocesses, the way
the skills do:

* ``test_runner.py`` (``/shipwright-test``), ``dev_server`` services, ``validate_env.py``,
  ``analyze_codebase.py`` + ``generate_adoption_artifacts.py`` (``/shipwright-adopt``).

Discovery (adopt's matcher: skip an invalid candidate with a warning) and selection (a run-config
profile or an explicit ``--profile``: must fail) are asserted separately, on purpose (D1).
Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py for the FR note).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.06")

REPO = Path(__file__).resolve().parents[1]
SHARED = REPO / "shared"
TEST_RUNNER = REPO / "plugins" / "shipwright-test" / "scripts" / "lib" / "test_runner.py"
VALIDATE_ENV = SHARED / "scripts" / "validate_env.py"
ANALYZE = REPO / "plugins" / "shipwright-adopt" / "scripts" / "tools" / "analyze_codebase.py"
GENERATE = REPO / "plugins" / "shipwright-adopt" / "scripts" / "tools" / "generate_adoption_artifacts.py"
BUNDLED_VITE_HONO = SHARED / "profiles" / "vite-hono.json"

DRIFT_CORE = ("unsupported schema_version 99", "supports stack-profile schema_version 1")


def _git(root: Path, *args: str) -> None:
    """Run git against ``root`` with the developer's own git setup neutralised: no global excludes file
    (it could ignore ``.shipwright``), and no ``GIT_DIR`` & co. inherited from a hook or worktree shell."""
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    subprocess.run(["git", "-C", str(root), "-c", "core.excludesFile=", "-c", "user.name=t",
                    "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True, text=True, env=env)


def _profile_data(name: str, **patch) -> dict:
    """A copy of the bundled vite-hono profile under a new name, with explicit test commands.

    Bundled node profiles declare unit/e2e without a ``command``; a copy must add one to every
    declared layer, otherwise /shipwright-test exits 3 (docs/stack-profiles.md)."""
    data = json.loads(BUNDLED_VITE_HONO.read_text(encoding="utf-8"))
    data["name"] = name
    testing = data.setdefault("testing", {})
    for layer in ("unit", "e2e"):
        entry = testing.get(layer)
        entry = dict(entry) if isinstance(entry, dict) else {}
        entry["command"] = f"echo {name}-{layer}"
        testing[layer] = entry
    data.update(patch)
    return data


def _make_project(tmp_path: Path, profile_name: str | None, data: dict | None = None) -> Path:
    """Main checkout with a committed project profile, then a worktree of it; returns the WORKTREE."""
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-b", "main")
    (main / "package.json").write_text(json.dumps({
        "name": "app", "dependencies": {"vite": "^5", "hono": "^4", "react": "^18"}}), encoding="utf-8")
    if profile_name:
        (main / "shipwright_run_config.json").write_text(json.dumps({"profile": profile_name}), encoding="utf-8")
        if data is not None:
            target = main / ".shipwright" / "profiles" / f"{data['name']}.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # What /shipwright-project writes: the managed gitignore (D10 keeps .shipwright/profiles/ trackable).
    canon = ("import sys; from pathlib import Path; sys.path.append(sys.argv[1]);"
             "from gitignore_canon import merge_canonical_block; merge_canonical_block(Path(sys.argv[2]))")
    _run("-c", canon, SHARED / "scripts" / "lib", main, cwd=main).check_returncode()
    _git(main, "add", ".")
    _git(main, "commit", "-m", "init")
    worktree = tmp_path / "worktree"
    _git(main, "worktree", "add", "-b", "feature", str(worktree))
    # D10: only the worktree copy may satisfy the asserts, so drop the main checkout's working copy.
    shutil.rmtree(main / ".shipwright" / "profiles", ignore_errors=True)
    return worktree


def _run(*argv: str | Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *map(str, argv)], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", timeout=180, check=False, env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def _json(done: subprocess.CompletedProcess) -> dict:
    return json.loads(done.stdout)


def _test_runner(wt: Path, layer: str = "unit") -> subprocess.CompletedProcess:
    return _run(TEST_RUNNER, "--layer", layer, "--cwd", wt, "--project-root", wt, cwd=wt)


def _validate_env(wt: Path) -> subprocess.CompletedProcess:
    return _run(VALIDATE_ENV, "--project-root", wt, "--phase", "build", cwd=wt)


# Private API on purpose: dev_server.py only has start/stop/status (it would START the services), so there is
# no public entry point that only reads the services. The 3-tuple (services, warnings, source) is pinned here
# and by shared/tests/test_dev_server_profile_resolution.py.
def _dev_server_services(wt: Path, name: str) -> subprocess.CompletedProcess:
    code = ("import json, sys; from pathlib import Path; sys.path.append(sys.argv[1]);"
            "from dev_server.profile_config import _get_services_resolved as g;"
            "services, warnings, source = g(sys.argv[2], Path(sys.argv[3]));"
            "print(json.dumps({'services': services, 'warnings': warnings, 'profile_source': source}))")
    return _run("-c", code, SHARED / "scripts", name, wt, cwd=wt)


def _analyze(wt: Path) -> subprocess.CompletedProcess:
    return _run(ANALYZE, "--project-root", wt, "--output", wt / "snapshot.json", cwd=wt)


def _generate(wt: Path, snapshot: Path, profile: str | None = None) -> subprocess.CompletedProcess:
    args = [GENERATE, "--project-root", wt, "--snapshot", snapshot, "--no-sync", "--no-backfill-events"]
    return _run(*args, *(["--profile", profile] if profile else []), cwd=wt)


def test_scaffold_runs_from_a_worktree_with_the_committed_profile(tmp_path):
    wt = _make_project(tmp_path, "my-stack", _profile_data("my-stack"))
    assert (wt / ".shipwright" / "profiles" / "my-stack.json").is_file()  # a fresh checkout sees it


def test_custom_project_profile_reports_source_project_in_every_loader(tmp_path):
    wt = _make_project(tmp_path, "my-stack", _profile_data("my-stack"))

    runner = _test_runner(wt)
    assert runner.returncode == 0, runner.stderr
    out = _json(runner)
    assert out["profile_source"] == "project" and out["command"] == "echo my-stack-unit"
    assert "source=project" in runner.stderr  # D8a: the source line precedes a command run

    dev = _dev_server_services(wt, "my-stack")
    assert dev.returncode == 0, dev.stderr
    assert _json(dev)["profile_source"] == "project"

    env = _validate_env(wt)
    assert _json(env)["profile_source"] == "project", env.stdout

    analyzed = _analyze(wt)
    assert analyzed.returncode == 0, analyzed.stderr
    profile = _json(analyzed)["profile"]
    assert profile["matched"] == "my-stack" and profile["source"] == "project"


def test_schema_version_too_new_stops_every_loader_with_the_same_message(tmp_path):
    wt = _make_project(tmp_path, "my-stack", _profile_data("my-stack", schema_version=99))

    runner = _test_runner(wt)
    assert runner.returncode == 3
    assert not _json(runner).get("success") and "echo" not in runner.stdout.replace('"command"', "")
    env = _validate_env(wt)
    assert env.returncode == 3 and _json(env)["kind"]
    dev = _dev_server_services(wt, "my-stack")
    assert dev.returncode != 0

    # selection by adopt (explicit --profile) fails the same way, nothing is written
    snapshot = wt / "snapshot.json"
    snapshot.write_text(json.dumps({"project_root": str(wt), "stack": {}, "profile": {"matched": "generic"}}),
                        encoding="utf-8")
    before = {p for p in wt.rglob("*") if p.is_file() and ".git" not in p.parts}
    adopt = _generate(wt, snapshot, "my-stack")
    assert adopt.returncode == 3
    assert {p for p in wt.rglob("*") if p.is_file() and ".git" not in p.parts} == before

    for label, text in (("test_runner", runner.stdout + runner.stderr), ("validate_env", env.stdout + env.stderr),
                        ("dev_server", dev.stdout + dev.stderr), ("adopt", adopt.stdout + adopt.stderr)):
        assert all(piece in text for piece in DRIFT_CORE), (label, text)
        assert "my-stack.json" in text, label  # the message names the file


def test_adopt_discovery_warns_excludes_the_candidate_and_continues(tmp_path):
    """DISCOVERY is not selection: with no run-config profile, an invalid candidate is skipped."""
    wt = _make_project(tmp_path, None)
    target = wt / ".shipwright" / "profiles" / "my-stack.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(_profile_data("my-stack", schema_version=99)), encoding="utf-8")

    analyzed = _analyze(wt)
    assert analyzed.returncode == 0, analyzed.stderr
    profile = _json(analyzed)["profile"]
    assert "my-stack" not in {c["name"] for c in profile["candidates"]}
    assert any("my-stack.json" in w and "skipped" in w and "unsupported schema_version 99" in w
               for w in profile["warnings"])
    assert profile["matched"] in {"vite-hono", "generic"}  # the bundled matcher carried on


def test_user_level_profile_is_used_when_the_project_has_none(tmp_path):
    user_dir = Path(os.environ["SHIPWRIGHT_USER_PROFILES_DIR"])
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "user-stack.json").write_text(json.dumps(_profile_data("user-stack")), encoding="utf-8")
    wt = _make_project(tmp_path, "user-stack")  # run config names it, the project does not carry it

    runner = _test_runner(wt)
    assert runner.returncode == 0, runner.stderr
    out = _json(runner)
    assert out["profile_source"] == "user" and out["command"] == "echo user-stack-unit"
    assert _json(_dev_server_services(wt, "user-stack"))["profile_source"] == "user"
    assert _json(_validate_env(wt))["profile_source"] == "user"
    matched = _json(_analyze(wt))["profile"]  # same stack metadata as vite-hono: the tie goes to the higher source (D1)
    assert (matched["matched"], matched["source"]) == ("user-stack", "user")


def test_shadowing_a_bundled_name_warns_and_skips_bundled_only_defaults(tmp_path):
    shadow = _profile_data("vite-hono")
    shadow["testing"].pop("integration", None)  # declares no integration layer
    wt = _make_project(tmp_path, "vite-hono", shadow)

    runner = _test_runner(wt)
    assert runner.returncode == 0, runner.stderr
    out = _json(runner)
    assert out["profile_source"] == "project" and out["command"] == "echo vite-hono-unit"  # own command (D9)
    assert "shadows" in runner.stderr  # D8b: prominent, at the loader

    integration = _test_runner(wt, "integration")
    skipped = _json(integration)
    assert integration.returncode == 0 and skipped.get("skipped") is True  # no bundled `npx` fallback
    assert "npx" not in json.dumps(skipped)

    dev = _dev_server_services(wt, "vite-hono")
    assert _json(dev)["profile_source"] == "project"
