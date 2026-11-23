"""``release.py record-event``: the Step 7 changelog event, in one call (unit P4).

Recorded BEFORE the merge so it ships in the release PR (an append after the merge strands uncommitted in the main checkout:
webui v0.28.0, monorepo v0.34.0). Same chain as the prose, stopping at the first tool that fails (the prose chained with
``&&``): ``record_event.py``, ``stage_event_drops.py``, ``git add`` of a tracked events file, a commit of ONLY the event paths
(``git diff --cached`` names them), and, on a feature branch, ``git push origin HEAD``. On the trunk the event is committed and
never pushed: the trunk is pushed once, with the tag. The branch kind is read from git here (the trunk check is today's
``main`` / ``develop``) and kept in the run state for the closing verify.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import release_paths, release_runstate
from .release_runner import Recorder, uv_script

TRUNKS = ("main", "develop")
EVENT_PATHS = ("shipwright_events.jsonl", ".shipwright/events/drops")


def record_event(rec: Recorder, plugin_root: Path, *, version: str, pr_url: str = "") -> tuple[int, dict[str, Any]]:
    shared, root = release_paths.shared_root(plugin_root), rec.cwd
    tools, run_id = shared / "scripts/tools", f"release-v{version}"
    branch = rec.run("branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    on_trunk = branch in TRUNKS
    detail = f"v{version} — tagged on main" if on_trunk else f"v{version} — {pr_url}"
    out: dict[str, Any] = {"version": version, "branch": branch, "on_trunk": on_trunk, "pr_url": pr_url, "committed": [], "pushed": False}
    if not on_trunk and not pr_url:  # nothing is recorded or pushed yet, and a pushed event cannot be taken back
        return 1, {**out, "status": "failed", "reason": "pr_url_missing", "commands": rec.as_json()}

    def stop(done, reason: str) -> tuple[int, dict[str, Any]]:
        release_runstate.patch(root, version, branch=branch, on_trunk=on_trunk, pr_url=pr_url)
        return done.exit or 1, {**out, "status": "failed", "reason": reason, "commands": rec.as_json()}

    for key, script, args in (("event-record", "record_event.py", ["--type", "phase_completed", "--phase", "changelog", "--run-id", run_id, "--detail", detail]),
                              ("event-stage", "stage_event_drops.py", ["--run-id", run_id])):
        done = rec.run(key, uv_script(tools / script, "--project-root", str(root), *args))
        if done.exit != 0:
            return stop(done, f"{key.replace('-', '_')}_failed")
    if (root / EVENT_PATHS[0]).is_file():
        rec.run("event-add", ["git", "add", EVENT_PATHS[0]])  # not part of the chain, as in the prose
    paths = [p for p in rec.run("event-paths", ["git", "diff", "--cached", "--name-only", "--", *EVENT_PATHS]).stdout.split() if p]
    if paths:
        done = rec.run("event-commit", ["git", "commit", "-m", f"chore(release): record changelog event for v{version}", "--", *paths])
        if done.exit != 0:
            return stop(done, "event_commit_failed")
        out["committed"] = paths
    if not on_trunk:
        done = rec.run("event-push", ["git", "push", "origin", "HEAD"])
        if done.exit != 0:
            return stop(done, "head_push_failed")
        out["pushed"] = True
    release_runstate.patch(root, version, branch=branch, on_trunk=on_trunk, pr_url=pr_url)
    return 0, {**out, "status": "ok", "commands": rec.as_json()}
