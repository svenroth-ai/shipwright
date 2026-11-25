"""``release.py record-event``: the Step 7 changelog event, in one call (unit P4).

Recorded BEFORE the merge so it ships in the release PR (an append after the merge strands uncommitted in the main checkout:
webui v0.28.0, monorepo v0.34.0). Same chain as the prose, stopping at the first tool that fails (the prose chained with
``&&``): ``record_event.py``, ``stage_event_drops.py``, ``git add`` of a tracked events file, a commit of ONLY the event paths
(``git diff --cached`` names them), and, on a feature branch, ``git push origin HEAD``. On the trunk the event is committed and
never pushed: the trunk is pushed once, with the tag. The branch kind is read from git here (a trunk is the remote's
default branch ``prepare`` stored, ``main`` or ``develop``; F5, ``trunks``) and kept in the run state, with the PR's base, for the closing verify.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import release_paths, release_runstate
from .release_runner import Recorder, uv_script

DEVELOP = "develop"  # the second trunk SKILL.md has always named next to the default branch
ALWAYS = ("main", DEVELOP)  # the trunks the prose named before F5 ("not main/develop"): F5 adds the remote's default, never removes one
UNKNOWN_EXTRA = ("master",)  # when the remote could not be asked, the other common default branch counts as a trunk too
_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}")  # a branch name that is safe in a push line and a --base value
LOOKUP = ["git", "-c", "credential.interactive=never", "ls-remote", "--symref", "origin", "HEAD"]  # the remote by NAME: no URL in argv
LOOKUP_ENV = {"GIT_TERMINAL_PROMPT": "0"}  # never a credential prompt that waits for a person
LOOKUP_TIMEOUT = 30  # seconds; a lookup that hangs falls back like one that fails


def trunk(rec: Recorder) -> tuple[str, str]:
    """F5 (D24): ``(default branch, source)``. Asked of the remote (``source`` ``remote``), else the local ``origin/HEAD``
    (``local``), else ``main`` (``fallback``). It is the PR base and one of the trunks (``trunks``). What the lookup printed is
    kept out of the JSON beyond the one line read: a remote's error text can name its URL, credentials included."""
    head = rec.run("trunk", LOOKUP, env=LOOKUP_ENV, timeout=LOOKUP_TIMEOUT)
    first = (head.stdout.splitlines() or [""])[0] if head.exit == 0 else ""
    rec.scrub_last(first, "" if head.exit == 0 else f"default-branch lookup failed (exit {head.exit})")
    words = first.split()
    found = words[1].removeprefix("refs/heads/") if len(words) > 1 and words[0] == "ref:" else ""
    if _BRANCH.fullmatch(found):
        return found, "remote"
    local = rec.run("trunk-local", ["git", "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD"])
    found = local.stdout.strip().removeprefix("origin/") if local.exit == 0 else ""
    return (found, "local") if _BRANCH.fullmatch(found) else ("main", "fallback")


def trunks(state: dict[str, Any]) -> tuple[str, ...]:
    """The branches a release is cut on directly, with no PR: the default branch ``prepare`` stored first (the PR base), then
    ``main`` and ``develop`` always, and ``master`` too when the default branch could not be asked (``trunk_source`` fallback)."""
    base = state.get("trunk")
    base = base if isinstance(base, str) and _BRANCH.fullmatch(base) else "main"
    extra = UNKNOWN_EXTRA if state.get("trunk_source") not in ("remote", "local") else ()
    return tuple(dict.fromkeys((base, *ALWAYS, *extra)))


def ensure_trunk(rec: Recorder, state: dict[str, Any]) -> dict[str, Any]:
    """``state`` with ``trunk`` and ``trunk_source``; asked now when a run state written before them lacks one."""
    if state.get("trunk") and state.get("trunk_source"):
        return state
    name, source = trunk(rec)
    return {**state, "trunk": name, "trunk_source": source}


def record_paths() -> tuple[str, str]:
    """The two event paths a release commits (the plugin cannot import the shared resolver: own lib package)."""
    return ("shipwright_events.jsonl", ".shipwright/events/drops")


def record_event(rec: Recorder, plugin_root: Path, *, version: str, pr_url: str = "") -> tuple[int, dict[str, Any]]:
    shared, root = release_paths.shared_root(plugin_root), rec.cwd
    tools, run_id = shared / "scripts/tools", f"release-v{version}"
    branch = rec.run("branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    stored = ensure_trunk(rec, release_runstate.stored(root, version) or {})  # a run state written before F5: ask the remote now
    on_trunk, base = branch in trunks(stored), trunks(stored)[0]
    detail = f"v{version} — tagged on {branch}" if on_trunk else f"v{version} — {pr_url}"
    out: dict[str, Any] = {"version": version, "branch": branch, "on_trunk": on_trunk, "pr_url": pr_url, "committed": [], "pushed": False}
    if not on_trunk and not pr_url:  # nothing is recorded or pushed yet, and a pushed event cannot be taken back
        return 1, {**out, "status": "failed", "reason": "pr_url_missing", "commands": rec.as_json()}

    def stop(done, reason: str) -> tuple[int, dict[str, Any]]:
        release_runstate.patch(root, version, branch=branch, on_trunk=on_trunk, pr_url=pr_url, trunk=stored["trunk"],
                               trunk_source=stored["trunk_source"], base_branch=None if on_trunk else base)
        return done.exit or 1, {**out, "status": "failed", "reason": reason, "commands": rec.as_json()}

    for key, script, args in (("event-record", "record_event.py", ["--type", "phase_completed", "--phase", "changelog", "--run-id", run_id, "--detail", detail]),
                              ("event-stage", "stage_event_drops.py", ["--run-id", run_id])):
        done = rec.run(key, uv_script(tools / script, "--project-root", str(root), *args))
        if done.exit != 0:
            return stop(done, f"{key.replace('-', '_')}_failed")
    event_paths = record_paths()
    if (root / event_paths[0]).is_file():
        rec.run("event-add", ["git", "add", event_paths[0]])  # not part of the chain, as in the prose
    listed = rec.run("event-paths", ["git", "diff", "--cached", "--name-only", "-z", "--", *event_paths])
    if listed.exit != 0:
        return stop(listed, "event_paths_failed")
    paths = [p for p in listed.stdout.split(chr(0)) if p]
    if paths:
        done = rec.run("event-commit", ["git", "commit", "-m", f"chore(release): record changelog event for v{version}", "--", *paths])
        if done.exit != 0:
            return stop(done, "event_commit_failed")
        out["committed"] = paths
    if not on_trunk:
        done = rec.run("event-push", ["git", "push", "origin", "HEAD", "--no-follow-tags"])  # never the tag: push.followTags would send it
        if done.exit != 0:
            return stop(done, "head_push_failed")
        out["pushed"] = True
    release_runstate.patch(root, version, branch=branch, on_trunk=on_trunk, pr_url=pr_url, trunk=stored["trunk"],
                           trunk_source=stored["trunk_source"], base_branch=None if on_trunk else base)
    return 0, {**out, "status": "ok", "commands": rec.as_json()}
