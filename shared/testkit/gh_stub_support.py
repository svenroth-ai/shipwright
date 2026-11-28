"""The argument and git plumbing of the ``gh`` stub (``gh_stub.py``), split out so the stub's commands stay under the 300-line cap.

Standard library only (ADR-044), like the stub: it runs in a scratch project's environment. Frozen with the stub (the golden lock
names both): a change to how flags are read or how git is run changes what every trace's ``gh`` call does.
"""

from __future__ import annotations

import os
import subprocess

_GIT = ["git", "-c", "user.name=gh-stub", "-c", "user.email=gh-stub@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]

SHORT: dict[tuple[str, str], dict[str, str]] = {
    ("pr", "create"): {"-t": "--title", "-b": "--body", "-B": "--base", "-H": "--head", "-F": "--body-file", "-R": "--repo"},
    ("pr", "merge"): {"-m": "--merge", "-d": "--delete-branch", "-s": "--squash", "-r": "--rebase", "-R": "--repo"},
    ("pr", "view"): {"-R": "--repo"},
    ("repo", "view"): {"-R": "--repo"},
    ("release", "create"): {"-t": "--title", "-n": "--notes", "-F": "--notes-file", "-d": "--draft", "-p": "--prerelease", "-R": "--repo"},
    ("release", "view"): {"-R": "--repo"},
}

_GIT_ENV_DROP = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")


def env() -> dict[str, str]:
    """The stub's merge commit is authored by the stub, not by the scenario's identity."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_DROP}


class Refusal(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def git_run(*args: str, cwd) -> subprocess.CompletedProcess:
    return subprocess.run([*_GIT, *args], cwd=str(cwd), env=env(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def git(*args: str, cwd, check: bool = True) -> str:
    done = git_run(*args, cwd=cwd)
    if check and done.returncode != 0:
        raise Refusal(f"git {' '.join(args)} failed: {(done.stderr or done.stdout).strip()}")
    return done.stdout.strip()


def flags(argv: list[str], valued: tuple[str, ...], bare_ok: tuple[str, ...] = (),
          short: dict[str, str] | None = None) -> tuple[list[str], dict[str, str], set[str]]:
    """Split ``argv`` into positionals, ``--name value`` pairs and bare flags. ``short`` is the command's own map."""
    positional, values, bare = [], {}, set()  # type: tuple[list[str], dict[str, str], set[str]]
    it = iter(argv)
    for arg in it:
        if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            if arg not in (short or {}):
                raise Refusal(f"gh-stub: unsupported flag {arg}", 2)  # a difference to recognise, not to guess at
            arg = short[arg]
        name, eq, inline = arg.partition("=")
        if name in valued:
            value = inline if eq else next(it, "")
            if not value or (not eq and value.startswith("--")):
                raise Refusal(f"gh-stub: flag {name} needs a value", 2)
            values[name] = value
        elif arg.startswith("--"):
            if arg not in bare_ok:
                raise Refusal(f"gh-stub: unsupported flag {name}", 2)  # a long flag the contract does not list
            bare.add(arg)
        else:
            positional.append(arg)
    return positional, values, bare
