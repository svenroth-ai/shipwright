"""Integration: the required-checks producer composes with the REAL SessionStart chain.

@FR-01.17

`cross_component` coverage for this change. The unit tests
(`test_check_required_checks_hook.py`) drive the wrapper with an injected runner and
prove its contract in isolation; that is exactly the shape which passes while the
composition is broken. What can only fail here is the join:

- the chain is `run_if_cache_ready.py` fanning out to N sibling hooks, and it
  propagates the FIRST non-zero child exit — so a producer that is individually
  fail-soft can still redden the chain through a sibling's contract;
- the chain re-emits child **stderr verbatim** and parses child **stdout** as
  SessionStart JSON — so a producer that is silent on its own can still corrupt the
  session's `additionalContext` once other hooks are contributing to it.

So this test reads the SessionStart command out of the shipped `hooks.json` and runs
**those targets, in that order**, through the real wrapper. A test that ran a
hand-built chain would prove the composition of something nobody ships.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "shipwright-iterate"
_HOOKS_JSON = _PLUGIN_ROOT / "hooks" / "hooks.json"
_RUNNER = _PLUGIN_ROOT / "scripts" / "hooks" / "run_if_cache_ready.py"

#: Text only the CHILD can produce. Two revisions were needed to get this right and
#: both mistakes are worth keeping visible:
#:
#: 1. The first draft matched only the drift paragraph (`Runs but gates nothing on` /
#:    `Configured but never reported`), which `render_drift` never emits in this
#:    fixture — the origin-less tree makes the producer exit 2 before it compares
#:    anything. Deleting `capture_output=True` would not have failed it.
#: 2. The second added the bare `[required-checks] ` prefix — but the WRAPPER's own
#:    `_warn` uses that identical prefix, so a legitimate wrapper warning (an
#:    unwritable throttle stamp, say) would fail this test with a message blaming
#:    the child's capture contract. A pattern that cannot tell the two apart cannot
#:    carry an assertion message that names one of them.
#:
#: 3. The third tried the producer's exit-2 texts ("no `origin` remote", "is not
#:    installed or not on PATH") — and those collide with a SIBLING hook in the same
#:    chain: `import_github_findings.py` legitimately prints "[github-api]
#:    owner_repo: no `origin` remote configured in …". Phrases about missing git
#:    remotes are common vocabulary among these producers, not a fingerprint.
#:
#: What is genuinely producer-only is the drift paragraph, so that is all this
#: matches. The complementary half — "only the WRAPPER may speak under the
#: `[required-checks]` prefix" — is a separate, precisely-worded assertion below,
#: because one regex cannot carry two different diagnoses.
_PRODUCER_PROSE = re.compile(r"Runs but gates nothing on|Configured but never reported")

#: Every message the wrapper itself is allowed to emit. Anything else under its
#: prefix came from the child, i.e. `capture_output` stopped holding.
_WRAPPER_MESSAGE_STEMS = (
    "producer exceeded",
    "producer could not be started",
    "producer exited",
    "could not record the throttle stamp",
    "could not resolve a project root",
)


def _pinned_env(project: Path) -> dict[str, str]:
    """Environment for a hook subprocess, with the project root PINNED.

    `lib.project_root.resolve_project_root` consults `SHIPWRIGHT_PROJECT_ROOT`
    **before** the working directory. Inheriting `os.environ` unmodified therefore
    lets these tests resolve the developer's REAL checkout — where `resolve_repo`
    finds a live `origin`, three authenticated `gh` calls go out against it, and the
    producer files a real card into their tree — while still passing, because the
    wrapper dutifully captures all of it and exits 0. `conftest.py` warns about this
    exact hazard and `test_hook_block_channel.py` pins the same variable for it.
    Pinning beats deleting: it also removes the cwd-resolution ambiguity.
    """
    env = dict(os.environ)
    env["SHIPWRIGHT_PROJECT_ROOT"] = str(project)
    # The throttle must not let a stamp from a previous test run skip the producer.
    env["SHIPWRIGHT_REQUIRED_CHECKS_THROTTLE_HOURS"] = "0.0000001"
    return env


def _registered_session_start_targets() -> list[Path]:
    """The chain as shipped: the runner's argv, resolved to real paths."""
    raw = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))
    events = raw.get("hooks", raw)
    blocks = events.get("SessionStart") or []
    commands = [h.get("command", "") for b in blocks for h in b.get("hooks", [])]
    assert commands, "shipwright-iterate registers no SessionStart hook"

    targets: list[Path] = []
    for command in commands:
        for token in shlex.split(command, posix=True):
            if not token.endswith(".py"):
                continue
            resolved = token.replace("${CLAUDE_PLUGIN_ROOT}", str(_PLUGIN_ROOT))
            path = Path(resolved).resolve()
            if path != _RUNNER.resolve():  # the runner drives the rest
                targets.append(path)
    return targets


def _git_only_path(bin_dir: Path) -> str | None:
    """Build a PATH on which `git` resolves and `gh` cannot.

    This is how "`gh` unavailable" is made real rather than assumed. Stripping PATH
    wholesale would break `git` too and send the producer down the no-remote branch
    again — the short-circuit that made the first version of this file never reach
    the `gh` leg at all.

    **Narrowing to git's OWN directory is not enough, and that mistake would have
    been invisible.** It works on Windows, where the two ship from separate
    installers — but on the `ubuntu-latest` runner `ci.yml` uses, `git` is
    `/usr/bin/git` and the preinstalled `gh` is `/usr/bin/gh`. Narrowing to
    `/usr/bin` hides nothing: the producer would resolve `o/r` from the fixture's
    origin and make a REAL `api.github.com` request, which 404s, which is a
    `GhError`, which is exit 2 — so every assertion here would still pass while the
    test did the one thing it must not do. Copying `git` into an otherwise-empty
    directory is what makes the isolation a property of the fixture rather than of
    the host's packaging.
    """
    git = shutil.which("git")
    if git is None:
        return None
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / Path(git).name
    try:
        shutil.copy2(git, target)
    except OSError:
        return None
    return str(bin_dir)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A Shipwright project with workflows but **no `origin` remote**.

    That is what keeps this hermetic: `resolve_repo` finds no remote and the producer
    takes its documented `exit 2` ("the configuration could not be read") without a
    single network call. It is also a real configuration — a fresh clone-less tree —
    rather than a mock of one.
    """
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}), encoding="utf-8"
    )
    (tmp_path / ".shipwright").mkdir()
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "name: CI\non:\n  pull_request:\n    branches: [main]\n"
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo hi\n",
        encoding="utf-8",
    )
    return tmp_path


def test_the_shipped_chain_runs_clean_with_the_producer_registered(project) -> None:
    """The composition: every registered hook, in order, through the real runner."""
    targets = _registered_session_start_targets()
    assert any("check_required_checks_hook.py" in t.name for t in targets), (
        "the producer is not in the shipped SessionStart chain, so this test would "
        "be certifying a composition that does not exist (trg-304c764b)"
    )

    payload = json.dumps({"session_id": "it-chain-test", "cwd": str(project)})
    done = subprocess.run(
        [sys.executable, str(_RUNNER), *[str(t) for t in targets]],
        input=payload.encode("utf-8"),
        capture_output=True,
        cwd=str(project),
        env=_pinned_env(project),
        timeout=180,
        check=False,
    )
    stdout = done.stdout.decode("utf-8", "replace")
    stderr = done.stderr.decode("utf-8", "replace")

    assert done.returncode == 0, (
        f"the SessionStart chain exited {done.returncode}. It propagates the first "
        f"non-zero child code, and a producer must never make a session fail.\n"
        f"stdout: {stdout}\nstderr: {stderr}"
    )
    assert not _PRODUCER_PROSE.search(stdout + stderr), (
        f"the producer's drift paragraph reached the session — the wrapper's "
        f"capture_output contract broke.\nstdout: {stdout}\nstderr: {stderr}"
    )
    # The other half, stated separately so each failure names its own cause: under
    # this prefix only the wrapper may speak. A line here that is not one of its
    # own messages is the child's stderr arriving uncaptured.
    foreign = [
        line for line in stderr.splitlines()
        if line.startswith("[required-checks] ")
        and not any(stem in line for stem in _WRAPPER_MESSAGE_STEMS)
    ]
    assert not foreign, (
        f"text appeared under the wrapper's prefix that the wrapper does not emit, "
        f"so it came from the producer through a broken capture: {foreign}"
    )
    if stdout.strip():
        # Whatever the chain emits must still be a valid SessionStart envelope: the
        # runner concatenates every hook's additionalContext into ONE payload, so a
        # single malformed contributor corrupts the others' output too.
        parsed = json.loads(stdout)
        specific = parsed["hookSpecificOutput"]
        assert specific["hookEventName"] == "SessionStart"
        assert isinstance(specific["additionalContext"], str)


def test_the_producer_is_reached_and_stays_silent_on_an_unreadable_host(project) -> None:
    """Isolates the new link: the wrapper alone, executed the way the chain executes it.

    Distinguishes "the chain was clean because the producer ran and said nothing" from
    "the chain was clean because the producer never ran" — the failure mode that would
    let the card's whole complaint survive this test suite.
    """
    hook = _REPO_ROOT / "shared" / "scripts" / "hooks" / "check_required_checks_hook.py"
    done = subprocess.run(
        [sys.executable, str(hook)],
        input=b"{}", capture_output=True, cwd=str(project),
        env=_pinned_env(project), timeout=120, check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert done.stdout == b"", (
        f"the wrapper wrote to stdout, which the chain parses as SessionStart JSON: "
        f"{done.stdout!r}"
    )
    # exit 2 is the routine "no gh / no remote" answer and must not be narrated.
    assert done.stderr == b"", f"routine unreadable-host path was noisy: {done.stderr!r}"


def test_it_stays_silent_when_gh_itself_is_unavailable(project, tmp_path) -> None:
    """AC-6's literal case, with the `gh` leg actually reached.

    The sibling tests above use an origin-less tree, so the producer exits 2 at
    `resolve_repo` and never calls `gh` — they prove one unreadable-host path, not
    this one, and they would pass on a host where `gh` is installed and logged in.
    Here the repository resolves (a real `git init` with a github.com origin) and
    PATH is narrowed so the very next step cannot find `gh`.
    """
    git_dir = _git_only_path(tmp_path / "nogh-bin")
    if git_dir is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("`git` is required in CI — install it before running this suite")
        pytest.skip("`git` not on PATH; install git or run from a shell that has it")

    repo = tmp_path / "resolvable"
    make = repo / ".github" / "workflows"
    make.mkdir(parents=True)
    (repo / "shipwright_run_config.json").write_text('{"status": "complete"}', "utf-8")
    (repo / ".shipwright").mkdir()
    (make / "ci.yml").write_text(
        "name: CI\non:\n  pull_request:\n    branches: [main]\njobs:\n"
        "  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )
    for argv in (["git", "init", "-q"],
                 ["git", "remote", "add", "origin", "https://github.com/o/r.git"]):
        subprocess.run(argv, cwd=str(repo), capture_output=True, check=True, timeout=60)

    env = _pinned_env(repo)
    env["PATH"] = git_dir
    # The precondition that turns a silent vacuum into a failure. Without it, a
    # host where `gh` sits beside `git` runs this whole test against the real
    # api.github.com and still goes green.
    assert shutil.which("git", path=env["PATH"]) is not None, "git must still resolve"
    assert shutil.which("gh", path=env["PATH"]) is None, (
        "PATH narrowing did not hide `gh`; this test would reach the network and "
        "pass for the wrong reason"
    )

    hook = _REPO_ROOT / "shared" / "scripts" / "hooks" / "check_required_checks_hook.py"
    done = subprocess.run(
        [sys.executable, str(hook)],
        input=b"{}", capture_output=True, cwd=str(repo), env=env,
        timeout=120, check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert done.stdout == b"", f"stdout must stay empty: {done.stdout!r}"
    assert done.stderr == b"", (
        f"a missing `gh` is the routine case this producer is built for and must "
        f"not be narrated: {done.stderr!r}"
    )
    # And it consumed its window, so the next session does not pay for it again.
    assert (repo / ".shipwright" / "required_checks_state.json").is_file()
