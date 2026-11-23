#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PreToolUse hook: no outward release action while a release is in progress and its record for HEAD is missing (P4b, B2).

Outward = ``git push`` of a tag or of the trunk, ``gh pr merge``, ``gh release create`` (``release_guard_commands``). The
hook is **inert** unless a release is in progress: ``release.py prepare`` wrote its run state (``release_run.json`` in the
git directory) less than 48 hours ago for this project root, and the release's tag is not on ``origin`` yet. An ordinary
push (a feature branch, no release running) never reaches the record check.

While active it requires ``.shipwright/runtime/release_state.json`` (written by ``release.py commit-and-tag``) for this
version, naming the release commit. HEAD must be that commit, or descend from it through the changelog event commit only
(``record-event`` runs after ``commit-and-tag`` and adds one commit that touches nothing but the event files). A record for
any other commit, or no record, blocks.

Fail-open: any error in this hook's own parsing or in the git calls that locate the state allows the command; only a remote that cannot be asked (the tag lookup) keeps a deny standing. ``SHIPWRIGHT_RELEASE_GUARD=off`` lifts it.
Cooperative enforcement against a forgetful model, not an adversarial boundary.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_guard_commands import Action, find_actions  # noqa: E402

RUN_STATE_GIT_PATH = "shipwright/release_run.json"
RECORD_REL = ".shipwright/runtime/release_state.json"
MAX_AGE_HOURS = 48  # the same bound release_runstate uses for an abandoned release
TRUNKS = ("main", "master", "develop")
_OFF_ENV = "SHIPWRIGHT_RELEASE_GUARD"
_SHA = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")
_TAG_LIKE = re.compile(r"v\d+\.\d+(\.\d+)?([-+.\w]*)")  # the release tag shape; a bare `2.0-hotfix` may be a branch


_NO_PROMPT = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}  # never wait on a login


def _git(cwd: Path, *args: str, timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                          env={**os.environ, **_NO_PROMPT})


def _posix_drive(part: str) -> str:
    """Git-Bash writes a Windows path as ``/c/Users/x``; git for Windows run by this hook needs ``C:/Users/x``."""
    found = re.fullmatch(r"/([A-Za-z])(/.*)?", part) if sys.platform == "win32" else None
    return f"{found.group(1).upper()}:{found.group(2) or '/'}" if found else part


def _effective_cwd(base: Path, action: Action) -> Path:
    cwd = base
    for part in action.c_paths:
        cwd = cwd / _posix_drive(part)  # an absolute part (also a Windows drive path) replaces the base
    return cwd


def _is_tag_push(cwd: Path, action: Action) -> bool:
    if action.tags:
        return True
    for ref in action.refs:
        if ref in TRUNKS or ref == "HEAD":
            continue
        if _TAG_LIKE.fullmatch(ref) or _git(cwd, "show-ref", "--verify", "--quiet", f"refs/tags/{ref}").returncode == 0:
            return True
    return False


def _is_trunk_push(cwd: Path, action: Action) -> bool:
    if action.all_refs or any(ref in TRUNKS for ref in action.refs):
        return True
    if action.refs and "HEAD" not in action.refs:
        return False
    branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()  # no refspec / HEAD: the current branch goes
    return branch in TRUNKS


def _is_outward(cwd: Path, action: Action) -> bool:
    if action.foreign:
        return False  # gh -R / --repo names another repository
    return action.kind != "push" or _is_tag_push(cwd, action) or _is_trunk_push(cwd, action)


def _is_this_releases_merge(cwd: Path, action: Action, state: dict) -> bool:
    """``gh pr merge`` of an unrelated PR is not the release's: only the release branch, its PR URL or number, or (no argument) the
    current branch when that is the release branch. Before ``record-event`` the state names no branch and every merge counts."""
    branch, url = state.get("branch"), state.get("pr_url") or ""
    if action.target:
        number = url.rstrip("/").rsplit("/", 1)[-1]
        return action.target in (branch, url) or (bool(number) and action.target == number)
    return not branch or _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == branch


def _active_state(cwd: Path) -> dict | None:
    """The run state of the release in progress that owns ``cwd``, else ``None``."""
    done = _git(cwd, "rev-parse", "--git-path", RUN_STATE_GIT_PATH)
    if done.returncode != 0 or not done.stdout.strip():
        return None
    path = Path(done.stdout.strip())
    path = path if path.is_absolute() else cwd / path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        made = datetime.fromisoformat(data["created_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("version"), str) or not data["version"]:
        return None
    if made.tzinfo is None:
        made = made.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - made).total_seconds() >= MAX_AGE_HOURS * 3600:
        return None
    root = data.get("project_root")
    if not isinstance(root, str) or not root:
        return None
    here = cwd.resolve()
    return data if here == Path(root).resolve() or Path(root).resolve() in here.parents else None


def _record_commit(root: Path, version: str) -> str | None:
    try:
        rec = json.loads((root / RECORD_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(rec, dict) and rec.get("version") == version and _SHA.fullmatch(str(rec.get("commit", "")))
    return rec["commit"] if ok else None


def _head_is_the_release(root: Path, commit: str) -> bool:
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    if head == commit:
        return True
    if not head or _git(root, "merge-base", "--is-ancestor", commit, head).returncode != 0:
        return False
    if _git(root, "rev-list", "--merges", f"{commit}..{head}").stdout.strip():
        return False
    names = _git(root, "log", "--name-only", "--format=", f"{commit}..{head}")  # each commit's own paths: a change and its revert is no event commit
    changed = [n.strip() for n in names.stdout.splitlines() if n.strip()]
    event_paths = ("shipwright_events.jsonl", ".shipwright/events/drops/")  # what record-event commits
    return names.returncode == 0 and all(n == event_paths[0] or n.startswith(event_paths[1]) for n in changed)


def _tag_is_on_origin(root: Path, version: str) -> bool:
    """True only when ``origin`` answered and holds the tag. Asked only on a would-be deny; a remote that cannot be asked
    (no origin, offline, auth) leaves the deny standing: the push or merge it would allow could not succeed either."""
    try:
        done = _git(root, "ls-remote", "--tags", "origin", f"refs/tags/v{version}", timeout=8)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and bool(done.stdout.strip())


def decide(command: str, base_cwd: Path) -> str | None:
    """The block reason for ``command``, or ``None`` to allow."""
    for action in find_actions(command):
        cwd = _effective_cwd(base_cwd, action)
        if not _is_outward(cwd, action):
            continue
        state = _active_state(cwd)
        if state is None:
            continue
        if action.kind == "merge" and not _is_this_releases_merge(cwd, action, state):
            continue
        root, version = Path(state["project_root"]), state["version"]
        commit = _record_commit(root, version)
        if commit and _head_is_the_release(root, commit):
            continue
        if _tag_is_on_origin(root, version):
            continue  # the release is out: nothing left to guard
        what = {"push": "git push of a tag or the trunk", "merge": "gh pr merge", "release": "gh release create"}[action.kind]
        have = f"its record names {commit[:10]}, not HEAD" if commit else f"{RECORD_REL} does not exist yet"
        return (f"Release v{version} is in progress and {have}: `{what}` would publish a release that `release.py commit-and-tag` "
                f"has not verified for this HEAD. Run `release.py commit-and-tag` (and `record-event`) first; if this release is "
                f"abandoned, ask the user to confirm first: only the user can lift this guard ({_OFF_ENV}=off in the session "
                f"environment, or removing {RUN_STATE_GIT_PATH} from the git directory).")
    return None


def main() -> int:
    try:
        if os.environ.get(_OFF_ENV, "").strip().lower() in {"off", "0", "false"}:
            return 0
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if payload.get("tool_name") not in ("Bash", "PowerShell") or not isinstance(command, str) or not command.strip():
            return 0
        cwd = payload.get("cwd")
        reason = decide(command, Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd())
    except Exception:  # noqa: BLE001 -- an ordinary push must never be blocked by a bug in this hook
        return 0
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
