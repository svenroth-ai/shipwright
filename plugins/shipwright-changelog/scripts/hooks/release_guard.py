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
version, naming the release commit. The commit judged is HEAD, or it must be that commit, or descend from it through the changelog
event commit only (``record-event`` runs after ``commit-and-tag`` and adds one commit that touches nothing but the event files; an
empty commit or a merge commit is not one). For a push that sends only a tag, and for ``gh release create``, the judged commit is
the tag's own (``refs/tags/v<version>``): ``gh pr merge`` leaves HEAD on the trunk at the merge commit, and SKILL.md Step 7 pushes
the tag after it. After a squash or rebase merge the record may also name the PR's merge commit (``published_commit`` with its proof,
D110): that commit passes too while its tree is still the audited release's (``release_merge_proof``, shared with the closing verify).
A record for any other commit, or no record, blocks.

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
import release_descent  # noqa: E402
import release_merge_proof  # noqa: E402
from release_guard_commands import Action, find_actions  # noqa: E402

RUN_STATE_GIT_PATH = "shipwright/release_run.json"
RECORD_REL = ".shipwright/runtime/release_state.json"
MAX_AGE_HOURS = 48  # the same bound release_runstate uses for an abandoned release
TRUNKS = ("main", "master", "develop")
_OFF_ENV = "SHIPWRIGHT_RELEASE_GUARD"
_SHA = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")
_TAG_LIKE = re.compile(r"v\d+\.\d+(\.\d+)?([-+.\w]*)")  # the release tag shape; a bare `2.0-hotfix` may be a branch


_NO_PROMPT = release_descent.NO_PROMPT  # never wait on a login (shared with the CLI's default-branch lookup)


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
    if not action.refs and action.named_tags:  # only tags go (`refs/tags/v1`, `tag v1`, `--tags`): no branch, so not the trunk (F-S3-1)
        return False
    branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()  # no refspec / HEAD: the current branch goes
    return branch in TRUNKS


def _judges_the_tag(cwd: Path, action: Action) -> bool:
    """A push that sends only tags (no trunk ref), or ``gh release create``: the tag's commit is the release, not HEAD."""
    return action.kind == "release" or (action.kind == "push" and not _is_trunk_push(cwd, action))


def _is_outward(cwd: Path, action: Action) -> bool:
    if action.foreign or action.cwd_unknown:
        return False  # gh -R / --repo names another repository; an unknown directory cannot be judged (fail open)
    return action.kind != "push" or _is_tag_push(cwd, action) or _is_trunk_push(cwd, action)


def _is_this_releases_merge(cwd: Path, action: Action, state: dict) -> bool:
    """``gh pr merge`` of an unrelated PR is not the release's: only the release branch, its PR URL or number, or (no argument) the
    current branch when that is the release branch. Before ``record-event`` the state names no branch and every merge counts."""
    branch, url = state.get("branch"), state.get("pr_url") or ""
    if action.target and not branch and not url:
        return True  # before record-event the release's PR is not known: a merge naming one counts
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


def _record(root: Path, version: str) -> dict | None:
    try:
        rec = json.loads((root / RECORD_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(rec, dict) and rec.get("version") == version and _SHA.fullmatch(str(rec.get("commit", "")))
    return rec if ok else None


def _is_the_release(root: Path, record: dict, tip: str) -> bool:
    """``tip`` is the record's commit, an event-only descendant of it (``release_descent``, shared with ``release.py push-tag``), or
    the record's proven merge commit (``release_merge_proof``, shared with the closing verify)."""
    def git(*args: str) -> tuple[int, str]:
        done = _git(root, *args)
        return done.returncode, done.stdout

    return release_merge_proof.accepts(git, record, tip)


def _judged_commit(root: Path, version: str, by_tag: bool) -> str:
    ref = f"refs/tags/v{version}^{{commit}}" if by_tag else "HEAD"
    found = _git(root, "rev-parse", "--verify", "-q", ref)
    if by_tag and found.returncode != 0:  # no local tag yet: nothing verified has been tagged, judge HEAD
        found = _git(root, "rev-parse", "HEAD")
    return found.stdout.strip()


def _tag_is_on_origin(root: Path, version: str) -> bool:
    """True only when ``origin`` answered and holds the tag. Asked only on a would-be deny; a remote that cannot be asked
    (no origin, offline, auth) leaves the deny standing: the push or merge it would allow could not succeed either."""
    try:
        done = _git(root, "ls-remote", "--tags", "origin", f"refs/tags/v{version}", timeout=8)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and bool(done.stdout.strip())


def _advice(record: dict | None, judged: str, version: str, by_tag: bool) -> str:
    subject = f"the tag v{version}" if by_tag and judged else "HEAD"
    if not record:
        return (f"{RECORD_REL} does not exist yet; run `release.py commit-and-tag` (and `record-event`) first")
    commit, merged = record["commit"], release_merge_proof.claimed(record)
    also = f", nor its merge commit {merged[:10]} with a proof that still holds" if merged else ""
    return (f"its record names {commit[:10]}, but {subject} is {judged[:10] or 'unknown'}, which is neither that commit nor an event-only "
            f"descendant of it{also}; check out the release commit or branch (the release was verified for {commit[:10]}), re-run "
            f"`release.py commit-and-tag` only if the release content changed")


def decide(command: str, base_cwd: Path) -> str | None:
    """The block reason for ``command``, or ``None`` to allow."""
    for action in find_actions(command):
        cwd = _effective_cwd(base_cwd, action)
        state = _active_state(cwd)  # first: no git call is made about a push while no release runs
        if state is None or not _is_outward(cwd, action):
            continue
        if action.kind == "merge" and not _is_this_releases_merge(cwd, action, state):
            continue
        root, version = Path(state["project_root"]), state["version"]
        record, by_tag = _record(root, version), _judges_the_tag(cwd, action)
        judged = _judged_commit(root, version, by_tag)
        if record and _is_the_release(root, record, judged):
            continue
        if _tag_is_on_origin(root, version):
            continue  # the release is out: nothing left to guard
        what = {"push": "git push of a tag or the trunk", "merge": "gh pr merge", "release": "gh release create"}[action.kind]
        return (f"Release v{version} is in progress and {_advice(record, judged, version, by_tag)}: `{what}` would publish a release "
                f"that has not been verified. If this release is abandoned, ask the user to confirm first: only the user can lift this "
                f"guard ({_OFF_ENV}=off in the session environment, or removing {RUN_STATE_GIT_PATH} from the git directory).")
    return None


def main() -> int:
    try:
        if os.environ.get(_OFF_ENV, "").strip().lower() in {"off", "0", "false"}:
            return 0
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
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
