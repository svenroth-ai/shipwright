"""``release.py push-tag``: the tag push of Step 7 and the decision before it, in one call (unit P5, carried over from P4).

The branching the prose used to describe is decided here from the run state (``record-event`` kept the branch kind):

- **F1a** from a feature branch only the tag goes out, never a local trunk (``git push origin refs/tags/vX``); on the trunk the
  trunk and exactly this tag go out in one push (``--tags`` would also push the orphan tags of refused releases).
- **F1b** in a hand-invoked release from a feature branch the tag goes out only once the release commit is on the PR's base branch on origin: a guided
  release leaves its PR open, so this refuses (``waiting_for_merge``, exit 1) until a person has merged it. Run it again then.
- **F4** a refused push ends the release (the push's own exit code); no PR, no event: ``record-event`` already refused.

Nothing is pushed unless ``commit-and-tag`` recorded this release's commit. The push happens inside this call, where the release guard hook
(``scripts/hooks/release_guard.py``, which reads Bash commands) cannot see it, so the trunk push keeps the guard's rule: HEAD may differ from the
release commit only by event files (``head_moved_since_release``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import release_commit, release_event, release_runstate, release_verify
from .release_runner import Recorder

EVENT_FILE, EVENT_DROPS = release_event.record_paths()[0], release_event.record_paths()[1] + "/"  # what `record-event` adds after the tag


def push_tag(rec: Recorder, plugin_root: Path, *, version: str) -> tuple[int, dict[str, Any]]:
    root, tag = rec.cwd, f"v{version}"
    state, record = release_runstate.stored(root, version) or {}, release_commit.read_state(root) or {}
    out: dict[str, Any] = {"version": version, "tag": tag, "pushed": False}

    def refuse(reason: str, code: int = 1, **more: Any) -> tuple[int, dict[str, Any]]:
        return code, {**out, **more, "status": "failed", "reason": reason, "commands": rec.as_json()}

    if record.get("version") != version:  # no release was cut: there is no tag to push
        return refuse("release_not_committed")
    branch = state.get("branch")
    if not branch:  # record-event keeps the branch kind: the push of a release whose event was never recorded would leave it out of the PR
        return refuse("event_not_recorded")
    if state.get("mode") not in ("pipeline", "standalone"):  # a rebuilt or damaged state must not read as a driven run (close-phase refuses it too)
        return refuse("run_state_missing")
    on_trunk = bool(state.get("on_trunk"))
    if on_trunk and branch not in release_event.TRUNKS:  # read from disk: never put an unchecked name into a push
        return refuse("branch_not_a_trunk")
    out.update(branch=branch, on_trunk=on_trunk)
    commit = record.get("commit")
    if not commit:
        return refuse("release_not_committed")
    named = rec.run("push-tag-commit", ["git", "rev-parse", "--verify", "-q", f"refs/tags/{tag}^{{commit}}"]).stdout.strip()
    if named != commit:  # a tag moved since commit-and-tag would publish another commit as the release
        return refuse("tag_not_the_release_commit", tag_commit=named)
    if on_trunk:
        if rec.run("push-head", ["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip() != branch:  # the check below reads HEAD, the push sends the branch
            return refuse("head_not_on_branch")
        moved = rec.run("push-moved", ["git", "diff", "--name-only", "-z", commit, "HEAD"])  # the trunk goes out too: only the release and its event
        extra = [p for p in moved.stdout.split(chr(0)) if p and p != EVENT_FILE and not p.startswith(EVENT_DROPS)]
        if moved.exit != 0 or extra:
            return refuse("head_check_failed" if moved.exit != 0 else "head_moved_since_release", moved.exit or 1, paths=extra[:5])
        argv = ["git", "push", "--end-of-options", "origin", f"refs/heads/{branch}", f"refs/tags/{tag}"]
    else:
        argv = ["git", "push", "origin", f"refs/tags/{tag}"]
    if not on_trunk and state.get("mode") == "standalone":  # a driven run never merges its PR (the master does): its tag goes out with the PR open
        reached, base, detail = release_verify.on_base(rec, state, commit)
        if not reached:
            return refuse("waiting_for_merge" if reached is False else "merge_state_unknown", base=base, detail=detail)
    done = rec.run("push-tags", argv)
    if done.exit != 0:
        return refuse("tag_push_failed", done.exit or 1)
    return 0, {**out, "pushed": True, "status": "ok", "commands": rec.as_json()}
