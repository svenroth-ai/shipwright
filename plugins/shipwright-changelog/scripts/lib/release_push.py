"""``release.py push-tag``: the decision before the tag push of Step 7 (unit P5). It never runs ``git push``.

The push stays one literal line in ``SKILL.md`` (BRIEF section 2, programme P4: outward commands are never moved behind a generic CLI), so
the release guard hook (``scripts/hooks/release_guard.py``) sees it. This call reads the run state and answers which line to run, or why none:

- ``status: "ok"`` with ``argv`` and ``line``: F1a. From a feature branch only the tag goes out (``git push origin refs/tags/vX``); on the
  trunk the trunk and exactly this tag go out together and all-or-nothing (``git push --atomic origin main refs/tags/vX``).
- ``status: "waiting_for_merge"`` (exit 1): F1b. A hand-invoked release (``mode: standalone``) from a feature branch pushes only once the
  release commit is on the PR's base branch on origin. A driven run (``mode: pipeline``) never merges its PR and never waits.
- ``status: "refused"`` (exit 1) with a ``reason``: no recorded release, no recorded event, a tag that names another commit, a trunk that moved
  by more than the event commit (the hook's rule, ``release_descent``), a PR merged without the release commit
  (``merged_without_release_commit``), or a merge state that could not be read.

The same ``release_verify.waits_for_merge`` answers "does this release wait" for the closing verify.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1] / "hooks"))  # appended: never shadow a module of the caller
import release_descent  # noqa: E402  (stdlib-only, shared with the release guard hook)

from . import release_commit, release_event, release_runstate, release_verify  # noqa: E402
from .release_runner import Recorder  # noqa: E402

SQUASHED = ("the PR was merged, but the release commit is not on {base}: the tag would name a commit that is not on the trunk "
            "(a squash or rebase merge). Nothing is pushed; an operator decides how to tag the merge commit")


def push_tag(rec: Recorder, plugin_root: Path, *, version: str) -> tuple[int, dict[str, Any]]:
    root, tag = rec.cwd, f"v{version}"
    state, record = release_runstate.stored(root, version) or {}, release_commit.read_state(root) or {}
    out: dict[str, Any] = {"version": version, "tag": tag}

    def answer(status: str, code: int, **more: Any) -> tuple[int, dict[str, Any]]:
        return code, {**out, **more, "status": status, "commands": rec.as_json()}

    def refuse(reason: str, **more: Any) -> tuple[int, dict[str, Any]]:
        return answer("refused", 1, reason=reason, **more)

    commit, branch = record.get("commit"), state.get("branch")
    if record.get("version") != version or not commit:  # no release was cut: there is no tag to push
        return refuse("release_not_committed")
    if not branch:  # record-event keeps the branch kind: a release whose event was never recorded would leave it out of the PR
        return refuse("event_not_recorded")
    if state.get("mode") not in ("pipeline", "standalone"):  # a rebuilt or damaged state must not read as a driven run (close-phase refuses it too)
        return refuse("run_state_missing")
    on_trunk = bool(state.get("on_trunk"))
    if on_trunk and branch not in release_event.TRUNKS:  # read from disk: never put an unchecked name into a push line
        return refuse("branch_not_a_trunk")
    out.update(branch=branch, on_trunk=on_trunk)
    named = rec.run("push-tag-commit", ["git", "rev-parse", "--verify", "-q", f"refs/tags/{tag}^{{commit}}"]).stdout.strip()
    if named != commit:  # a tag moved since commit-and-tag would publish another commit as the release
        return refuse("tag_not_the_release_commit", tag_commit=named)
    if on_trunk:
        if rec.run("push-head", ["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip() != branch:  # the rule below reads HEAD, the push sends the branch
            return refuse("head_not_on_branch")

        def git(*args: str) -> tuple[int, str]:
            done = rec.run("push-git", ["git", *args])
            return done.exit, done.stdout

        if not release_descent.is_the_release(git, commit, rec.run("push-tip", ["git", "rev-parse", "HEAD"]).stdout.strip()):
            return refuse("head_moved_since_release")
        argv = ["git", "push", "--atomic", "origin", branch, f"refs/tags/{tag}"]
    else:
        argv = ["git", "push", "origin", f"refs/tags/{tag}"]
        if release_verify.waits_for_merge(state):
            reached, base, detail = release_verify.on_base(rec, state, commit)
            if reached is None:
                return refuse("merge_state_unknown", base=base, detail=detail)
            if not reached:
                pr_state = _pr_state(rec, state)
                if pr_state == "MERGED":  # waiting would never end: ancestry cannot prove a squash or rebase merge
                    return refuse("merged_without_release_commit", base=base, detail=SQUASHED.format(base=base))
                if pr_state == "CLOSED":  # closed without a merge: it will not get merged by waiting
                    return refuse("pr_closed_unmerged", base=base, detail="the PR was closed without being merged; nothing is pushed")
                return answer("waiting_for_merge", 1, reason="waiting_for_merge", base=base, detail="the PR is not merged yet; run this again after the merge")
    return answer("ok", 0, argv=argv, line=" ".join(argv))


def _pr_state(rec: Recorder, state: dict[str, Any]) -> str:
    """``gh pr view``: the release PR's state (``MERGED`` in any way, ``CLOSED``, ``OPEN``). Unknown, unreadable or no PR URL is ``""``."""
    url = state.get("pr_url")
    if not url:
        return ""
    done = rec.run("push-pr-view", ["gh", "pr", "view", url, "--json", "state,mergeCommit"])
    try:
        found = json.loads(done.stdout)
    except ValueError:
        return ""
    return str(found.get("state") or "") if done.exit == 0 and isinstance(found, dict) else ""
