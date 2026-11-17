"""A scratch project for release scenarios: ``minimal_valid_project`` + git + a bare ``origin``.

Standard library only (ADR-044). Builds, under one temp directory:

* ``repo/``       the project: the minimal valid project's phases, one git repository, an
                  initial commit and (optionally) the ``v0.1.0`` release commit and tag;
* ``origin.git/`` a local bare repository. ``origin``'s FETCH url is a fake GitHub one
                  (so ``resolve_repo_identity`` answers ``acme-fixture/widgets``); its PUSH url
                  is the bare repository, so ``git push`` really lands somewhere;
* ``stub/``       the state directory of ``gh_stub.py`` (``state.json`` + ``argv.jsonl``).

**The environment is built, never inherited** (programme P7a). :func:`build_env` starts from
an allowlist of what a process needs to run at all, drops everything else (so no API key and
no ``SHIPWRIGHT_ROOT``), and sets ``GIT_ALLOW_PROTOCOL=file`` (the fake ``https`` fetch url is
refused at once: git cannot reach the network; ``uv`` and ``urllib`` children are NOT fenced), a private
empty git config and an empty user home, a fixed identity and the ``gh`` seam. A bare ``gh`` resolves to a
shim first; on Windows ``CreateProcess`` finds ``gh.exe`` through the PARENT's PATH, so the real ``gh`` stays
reachable there, logged out and aimed at ``GH_HOST=gh.invalid``: a replay driver must route every ``gh``
through the seam. :func:`assert_no_secrets` fails the build when any secret-shaped name
is present, whether it came from the parent or from ``extra``.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import minimal_valid_project as mvp

FAKE_SLUG = "acme-fixture/widgets"
FAKE_ORIGIN_URL = f"https://github.com/{FAKE_SLUG}.git"
GH_STUB = Path(__file__).resolve().with_name("gh_stub.py")

# What a process needs to run at all. Everything else in the parent environment is dropped.
_PASS_THROUGH = (  # no HOME: build_env points it at an empty directory
    "PATH", "PATHEXT", "SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "ProgramFiles", "ProgramFiles(x86)",
    "ProgramW6432", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR",
)
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSW|(?:^|_)(?:PAT|PWD)(?:_|$)|CREDENTIAL|(?:^|_)AUTH(?:_|$))", re.IGNORECASE)
# A named exception, with its reason: a DUMMY token (only this exact value passes) makes a real ``gh`` that slips
# past the shim answer 401 from the dead host instead of reading the operator's keyring token.
DUMMY_GH_TOKEN = "gh-stub-dummy-token-not-a-credential"
_SECRET_ALLOWED: dict[str, str] = {"GH_TOKEN": DUMMY_GH_TOKEN, "GH_ENTERPRISE_TOKEN": DUMMY_GH_TOKEN}
_LAYOUTS = ("legacy", "drops")


class EnvLeak(AssertionError):
    """A secret-shaped or forbidden variable is in a scenario environment."""


def assert_no_secrets(env: Mapping[str, str]) -> None:
    bad = sorted(name for name in env
                 if (_SECRET_NAME.search(name) and _SECRET_ALLOWED.get(name) != env[name]) or name == "SHIPWRIGHT_ROOT")
    if bad:
        raise EnvLeak(f"scenario environment leaks: {', '.join(bad)}")


def _uv_dirs(source: Mapping[str, str], platform: str) -> dict[str, str]:
    """uv's cache and Python dirs of the PARENT on Linux/macOS (the scratch's empty HOME would hide them): without
    them ``uv --offline run`` finds a cold cache. Windows passes LOCALAPPDATA through; a dir that does not exist stays unset."""
    if platform.startswith("win") or not source.get("HOME"):
        return {}
    home = Path(source["HOME"])
    mac = platform == "darwin"
    cache = Path(source["XDG_CACHE_HOME"]) / "uv" if source.get("XDG_CACHE_HOME") and not mac else (
        home / "Library" / "Caches" / "uv" if mac else home / ".cache" / "uv")
    data = Path(source["XDG_DATA_HOME"]) if source.get("XDG_DATA_HOME") else home / ".local" / "share"
    found = {"UV_CACHE_DIR": cache, "UV_PYTHON_INSTALL_DIR": data / "uv" / "python"}
    return {name: str(path) for name, path in found.items() if name not in source and path.is_dir()}


def _path_with_shims(path: str, shim_dir: Path) -> str:
    """PATH with the stub's shim directory first. A folder is dropped only when it holds nothing but a real gh
    (on Linux ``/usr/bin`` holds gh, git and sh: it stays; there the shim wins by order)."""
    keep = [d for d in path.split(os.pathsep) if d and not _only_a_real_gh(Path(d))]
    return os.pathsep.join([str(shim_dir), *keep])


def _only_a_real_gh(folder: Path) -> bool:
    """A folder that holds a gh and no git or sh (the GitHub CLI's own folder): dropping it hides nothing else."""
    has = lambda names: any((folder / n).exists() for n in names)  # noqa: E731
    return has(("gh", "gh.exe", "gh.cmd", "gh.bat")) and not has(("git", "git.exe", "sh", "sh.exe", "python", "python.exe"))


def _write_gh_shims(shim_dir: Path) -> None:
    """A bare ``gh`` (typed by a person or a model) lands on the stub. ``gh.cmd`` serves a shell on Windows."""
    shim_dir.mkdir(parents=True, exist_ok=True)
    py, stub = sys.executable, GH_STUB
    sh = '#!/bin/sh\nexec "{}" "{}" "$@"\n'.format(Path(py).as_posix(), stub.as_posix())
    cmd = '@echo off\r\n"{}" "{}" %*\r\n'.format(py, stub)
    (shim_dir / "gh").write_bytes(sh.encode("utf-8"))
    (shim_dir / "gh").chmod(0o755)
    (shim_dir / "gh.cmd").write_bytes(cmd.encode("utf-8"))


def build_env(stub_state: Path, *, events_layout: str | None = None,
              extra: Mapping[str, str] | None = None, parent: Mapping[str, str] | None = None) -> dict[str, str]:
    """The explicit environment of every command a scenario spawns."""
    if events_layout not in (None, *_LAYOUTS):
        raise ValueError(f"events_layout must be one of {_LAYOUTS} or None, not {events_layout!r}")
    source = os.environ if parent is None else parent
    env = {name: source[name] for name in _PASS_THROUGH if name in source}
    env.update(_uv_dirs(source, sys.platform))
    shim_dir = stub_state / "bin"
    env["PATH"] = _path_with_shims(source.get("PATH", ""), shim_dir)
    _write_gh_shims(shim_dir)
    git_config = stub_state / "empty.gitconfig"
    git_config.parent.mkdir(parents=True, exist_ok=True)
    git_config.write_text("", encoding="utf-8")
    home = stub_state / "home"  # an empty user home: no operator profiles, keys or git config
    home.mkdir(parents=True, exist_ok=True)
    env.update(
        HOME=str(home), USERPROFILE=str(home), XDG_CONFIG_HOME=str(home),
        GH_HOST="gh.invalid",  # a real gh that slips through targets a host that does not exist
        GH_TOKEN=DUMMY_GH_TOKEN, GH_ENTERPRISE_TOKEN=DUMMY_GH_TOKEN,  # ... and is refused there, not logged in as the operator
        GIT_ALLOW_PROTOCOL="file", GIT_TERMINAL_PROMPT="0",
        GIT_CONFIG_GLOBAL=str(git_config),  # no GIT_CONFIG_NOSYSTEM: Git for Windows reads its own system config (e.g. the ssl/credential helper) from there; the global file is the isolated one
        LANG="C", LC_ALL="C",
        GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid",
        PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
        SHIPWRIGHT_TEST_GH_ARGV_PREFIX=json.dumps([sys.executable.replace("\\", "/"), GH_STUB.as_posix()]),
        SHIPWRIGHT_GH_STUB_STATE=str(stub_state),
        GH_CONFIG_DIR=str(stub_state / "gh-config"), GH_PROMPT_DISABLED="1",  # a real gh would be logged out
    )
    if events_layout:  # a scenario pins one layout; None leaves both variables unset (replay, L3)
        env.update(SHIPWRIGHT_EVENTS_LAYOUT=events_layout, SHIPWRIGHT_EVENTS_LAYOUT_TEST="1")
    env.update(extra or {})
    assert_no_secrets(env)
    return env


@contextlib.contextmanager
def _isolated_user_config(home: Path):
    """``minimal_valid_project`` runs its git calls under the process environment: give them an empty user config."""
    names = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "GIT_CONFIG_NOSYSTEM")
    saved = {n: os.environ.get(n) for n in names}
    home.mkdir(parents=True, exist_ok=True)
    os.environ.update(HOME=str(home), USERPROFILE=str(home), XDG_CONFIG_HOME=str(home), GIT_CONFIG_NOSYSTEM="1")
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@dataclass(frozen=True)
class Scratch:
    root: Path
    repo: Path
    origin: Path
    stub_state: Path
    env: dict[str, str]

    @property
    def argv_log_path(self) -> Path:
        return self.stub_state / "argv.jsonl"

    def run(self, argv: Sequence[str], *, timeout: float = 300, check: bool = False) -> subprocess.CompletedProcess:
        """Run a command in the scratch repo (cwd) under the built environment."""
        return subprocess.run(list(argv), cwd=str(self.repo), env=self.env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, check=check)

    def git(self, *args: str) -> str:
        return self.run(["git", *args], check=True).stdout.strip()

    def gh_argv_log(self) -> list[dict]:
        if not self.argv_log_path.is_file():
            return []
        return [json.loads(ln) for ln in self.argv_log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def gh_state(self) -> dict:
        path = self.stub_state / "state.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"prs": [], "releases": {}}


def build_scratch(root: Path, *, tagged: bool = True, default_branch: str = "main",
                  events_layout: str | None = None) -> Scratch:
    """Build the scratch project. ``tagged=False`` is a repo with no release yet (no ``v0.1.0``)."""
    root.mkdir(parents=True, exist_ok=True)
    repo, origin, stub = root / "repo", root / "origin.git", root / "stub"
    repo.mkdir()
    stub.mkdir()
    env = build_env(stub, events_layout=events_layout)
    scratch = Scratch(root=root, repo=repo, origin=origin, stub_state=stub, env=env)
    subprocess.run(["git", "init", "--bare", "-q", "-b", default_branch, str(origin)], env=env, check=True,
                   capture_output=True, timeout=60)
    scratch.git("init", "-q", "-b", default_branch)
    for key, value in (("commit.gpgsign", "false"), ("tag.gpgsign", "false"), ("core.autocrlf", "false"),
                       ("core.hooksPath", str(stub / "no-hooks"))):
        scratch.git("config", key, value)
    with _isolated_user_config(stub / "home"):
        for phase, split in (("project", None), ("design", None), ("plan", "01-core"),
                             ("build", "01-core"), ("test", "01-core")):
            mvp.write_phase(repo, phase, split)
        scratch.git("add", "-A")
        scratch.git("commit", "-q", "-m", "chore: initial project")
        if tagged:
            mvp.write_phase(repo, "changelog")  # commits "release 0.1.0" and tags v0.1.0, then writes its canon
    if scratch.git("status", "--porcelain"):  # the canon a phase writes after its commit: start from a clean tree
        scratch.git("add", "-A")
        scratch.git("commit", "-q", "-m", "chore: record phase state")
    scratch.git("remote", "add", "origin", FAKE_ORIGIN_URL)
    scratch.git("config", "remote.origin.pushurl", origin.as_posix())
    scratch.git("push", "-q", "origin", default_branch)
    if tagged:
        scratch.git("push", "-q", "origin", "--tags")
    return scratch
