"""The scratch project and its explicitly built environment (golden-trace harness)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.covers("FR-01.09/AC14")  # test support for the changelog pilot (programme P2a); the gate refuses removing it (tag-removed), see the P2b1 FINDINGS note
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "testkit"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

import release_scratch as rs  # noqa: E402
from repo_identity import resolve_repo_identity  # noqa: E402

_LEAKY = {"OPENROUTER_API_KEY": "k1", "OPENAI_API_KEY": "k2", "ANTHROPIC_API_KEY": "k3", "GH_TOKEN": "t1", "GH_ENTERPRISE_TOKEN": "t3",
          "GITHUB_TOKEN": "t2", "AWS_SECRET_ACCESS_KEY": "s", "SHIPWRIGHT_ROOT": "/dev/checkout",
          "SHIPWRIGHT_EVENTS_LAYOUT": "drops"}


@pytest.fixture
def scratch(tmp_path: Path) -> rs.Scratch:
    return rs.build_scratch(tmp_path / "s")


def test_the_scratch_is_a_git_repo_with_a_bare_origin_and_a_fake_github_url(scratch):
    assert (scratch.repo / ".git").is_dir() and scratch.origin.name == "origin.git"
    assert scratch.git("remote", "get-url", "origin") == rs.FAKE_ORIGIN_URL
    assert scratch.git("remote", "get-url", "--push", "origin") == scratch.origin.as_posix()
    assert resolve_repo_identity(scratch.repo) == rs.FAKE_SLUG
    assert scratch.git("log", "-1", "--format=%s") == "chore: record phase state"
    assert scratch.git("status", "--porcelain") == ""
    assert scratch.git("log", "-1", "--format=%s", "v0.1.0") == "release 0.1.0"
    assert scratch.git("tag") == "v0.1.0"


def test_the_bare_origin_starts_in_step_with_the_project(scratch):
    refs = scratch.git("ls-remote", scratch.origin.as_posix())
    assert scratch.git("rev-parse", "HEAD") in refs and "refs/tags/v0.1.0" in refs
    head = scratch.run(["git", "push", "origin", "HEAD:refs/heads/feat/y"])  # the push url works
    assert head.returncode == 0, head.stderr


def test_an_untagged_scratch_has_no_release_and_a_master_default_is_honoured(tmp_path):
    s = rs.build_scratch(tmp_path / "u", tagged=False, default_branch="master")
    assert s.git("tag") == "" and s.git("rev-parse", "--abbrev-ref", "HEAD") == "master"
    assert s.git("log", "-1", "--format=%s") == "chore: initial project"
    assert "refs/heads/master" in s.git("ls-remote", s.origin.as_posix())


def test_nothing_in_the_fetch_path_can_reach_the_network(scratch):
    done = scratch.run(["git", "fetch", "origin"])
    assert done.returncode != 0 and "not allowed" in done.stderr


def test_build_env_drops_every_key_and_secret_of_the_parent(tmp_path):
    env = rs.build_env(tmp_path, parent={**_LEAKY, "PATH": "/bin"})
    assert env["PATH"].split(os.pathsep)[1:] == ["/bin"]  # the stub shim directory comes first
    assert not set(_LEAKY) - set(rs._SECRET_ALLOWED) & set(env) and not {"t1", "t3"} & set(env.values())
    assert env["GIT_ALLOW_PROTOCOL"] == "file" and "GIT_CONFIG_NOSYSTEM" not in env


def test_no_seeded_credential_value_survives_and_the_parent_is_left_alone(tmp_path, monkeypatch):
    for name, value in _LEAKY.items():
        monkeypatch.setenv(name, "seeded-" + value)
    before = dict(os.environ)
    env = rs.build_env(tmp_path)
    assert not any(v.startswith("seeded-") for v in env.values())
    assert env["GH_TOKEN"] == env["GH_ENTERPRISE_TOKEN"] == rs.DUMMY_GH_TOKEN  # a stray real gh is refused, not the operator
    assert env["LC_ALL"] == "C" and "SHIPWRIGHT_ROOT" not in env
    assert dict(os.environ) == before  # GIT_ALLOW_PROTOCOL and the seam are for the child only


def test_a_hostile_user_git_config_does_not_reach_the_scratch(tmp_path, monkeypatch):
    home = tmp_path / "home"
    hooks = home / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    config = f"[core]\n\thooksPath = {hooks.as_posix()}\n[commit]\n\tgpgsign = true\n[user]\n\tsigningkey = nothere\n"
    (home / ".gitconfig").write_text(config, encoding="utf-8")
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(home))
    s = rs.build_scratch(tmp_path / "s")
    assert s.git("log", "-1", "--format=%an") == "fixture"
    s.git("commit", "-q", "--allow-empty", "-m", "chore: again")  # no hook, no signing
    assert (os.environ["HOME"], os.environ["USERPROFILE"]) == (str(home), str(home))  # restored


def test_a_child_process_of_the_scratch_sees_no_key_and_runs_in_the_repo(scratch, monkeypatch):
    for name, value in _LEAKY.items():
        monkeypatch.setenv(name, value)
    code = "import os,json;print(json.dumps([sorted(os.environ), os.getcwd()]))"
    done = scratch.run([sys.executable, "-c", code], check=True)
    import json
    names, cwd = json.loads(done.stdout)
    assert not set(_LEAKY) - set(rs._SECRET_ALLOWED) & set(names)
    assert Path(cwd).resolve() == scratch.repo.resolve()


def test_the_dummy_gh_token_is_the_only_value_allowed_for_a_gh_token_name(tmp_path):
    rs.assert_no_secrets({"GH_TOKEN": rs.DUMMY_GH_TOKEN})
    with pytest.raises(rs.EnvLeak, match="GH_TOKEN"):
        rs.build_env(tmp_path, extra={"GH_TOKEN": "a-real-looking-token"})


def test_uv_dirs_of_the_parent_pass_through_on_linux_and_macos_only_when_set_and_present(tmp_path):
    home = tmp_path / "h"
    (home / ".cache" / "uv").mkdir(parents=True)
    (home / ".local" / "share" / "uv" / "python").mkdir(parents=True)
    got = rs._uv_dirs({"HOME": str(home)}, "linux")
    assert got == {"UV_CACHE_DIR": str(home / ".cache" / "uv"),
                   "UV_PYTHON_INSTALL_DIR": str(home / ".local" / "share" / "uv" / "python")}
    assert rs._uv_dirs({"HOME": str(home), "UV_CACHE_DIR": "/x"}, "linux").keys() == {"UV_PYTHON_INSTALL_DIR"}
    assert rs._uv_dirs({"HOME": str(home)}, "win32") == {} and rs._uv_dirs({}, "linux") == {}
    (home / "Library" / "Caches" / "uv").mkdir(parents=True)
    assert rs._uv_dirs({"HOME": str(home)}, "darwin")["UV_CACHE_DIR"] == str(home / "Library" / "Caches" / "uv")
    assert rs._uv_dirs({"HOME": str(tmp_path / "none")}, "linux") == {}


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not on PATH")
def test_uv_still_runs_offline_inside_a_scratch(scratch):
    done = scratch.run(["uv", "--offline", "run", "--no-project", "python", "-c", "print(40 + 2)"])
    assert done.returncode == 0 and done.stdout.strip() == "42", done.stderr


@pytest.mark.parametrize("name", ["OPENROUTER_API_KEY", "GH_TOKEN", "MY_SERVICE_SECRET", "DB_PASSWORD", "SSH_AUTH_SOCK",
                                  "SHIPWRIGHT_ROOT"])
def test_a_leaked_name_fails_the_build_even_when_added_on_purpose(tmp_path, name):
    with pytest.raises(rs.EnvLeak, match=name):
        rs.build_env(tmp_path, extra={name: "x"})


def test_the_leak_check_does_not_flag_the_harness_own_variables(tmp_path):
    rs.assert_no_secrets(rs.build_env(tmp_path, events_layout="drops"))  # GIT_AUTHOR_NAME is not an AUTH secret


def test_the_gh_seam_points_at_the_stub_and_the_layout_is_pinned_only_on_request(tmp_path):
    plain = rs.build_env(tmp_path)
    assert "SHIPWRIGHT_EVENTS_LAYOUT" not in plain and "SHIPWRIGHT_EVENTS_LAYOUT_TEST" not in plain
    assert plain["SHIPWRIGHT_GH_STUB_STATE"] == str(tmp_path)
    pinned = rs.build_env(tmp_path, events_layout="legacy")
    assert (pinned["SHIPWRIGHT_EVENTS_LAYOUT"], pinned["SHIPWRIGHT_EVENTS_LAYOUT_TEST"]) == ("legacy", "1")
    with pytest.raises(ValueError):
        rs.build_env(tmp_path, events_layout="both")


def test_scratch_hooks_are_off_and_the_secret_check_knows_pat_and_pwd_but_not_path(scratch):
    assert scratch.git("config", "core.hooksPath").endswith("no-hooks")
    for name in ("GH_PAT", "DB_PWD"):
        with pytest.raises(rs.EnvLeak):
            rs.assert_no_secrets({name: "x"})
    rs.assert_no_secrets({"PATH": "/bin", "PYTHONPATH": "x", "GIT_AUTHOR_NAME": "x"})


def test_a_child_process_gets_an_empty_home_inside_the_scratch_and_a_dead_gh_host(scratch):
    done = scratch.run([sys.executable, "-c", "import pathlib;print(pathlib.Path.home())"], check=True)
    assert Path(done.stdout.strip()).resolve() == (scratch.stub_state / "home").resolve()
    assert scratch.env["GH_HOST"] == "gh.invalid"


def test_only_a_folder_holding_nothing_but_a_real_gh_is_dropped_from_path(tmp_path):
    gh_only, with_git = tmp_path / "ghcli", tmp_path / "usrbin"
    gh_only.mkdir()
    with_git.mkdir()
    for folder, names in ((gh_only, ["gh.exe", "gh"]), (with_git, ["gh", "git", "sh"])):
        for name in names:
            (folder / name).write_text("", encoding="utf-8")
    shim = tmp_path / "shims"
    path = os.pathsep.join([str(gh_only), str(with_git)])
    assert rs._path_with_shims(path, shim).split(os.pathsep) == [str(shim), str(with_git)]
