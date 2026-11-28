"""``release.py merge-ready``: which merge line an autonomous release runs in Step 7 (unit U4, FINDINGS D110). It never merges.

The merge stays one literal line in ``SKILL.md`` (``gh pr merge --{method} --match-head-commit {head} --delete-branch``), so the release
guard hook sees it; this call reads the run state, the release record and the repository and answers which line to run, or why none:

- ``method``: from ``gh repo view --json mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed``. A merge commit is preferred (the tag
  stays on the release commit, nothing to prove); else squash, else rebase (``release.py push-tag`` proves either after the merge, unit U3).
  The repository's settings are read, never changed (operator decision 2026-11-28).
- ``head``: the PR head the release was verified for, always pinned (``--match-head-commit``): HEAD is the release commit or its event
  commit (``release_descent``, the guard's rule) and the PR's head on the host is that same commit. A commit pushed to the branch since makes
  the host refuse the merge instead of merging what was never audited.
- Before a squash or rebase merge the freshly fetched base must be an ancestor of the head. If the base moved, the merge commit would
  carry code the release does not describe (D112), and push-tag would stop after the merge with ``foreign_commits_on_base``. So this
  stops first with ``base_moved``: nothing is merged, and the operator restarts the release by hand. Nothing updates the branch here
  (``gh pr update-branch`` would put a commit past the release on the PR head and break push-tag's proof).
  The check is best-effort: a PR merged into the base between this answer and the merge is not caught here; push-tag's proof after the
  merge stops on it (``foreign_commits_on_base``, unit U3), which stays the backstop.

A refusal is exit 1 with a ``reason`` and a plain ``detail``; ``repo_settings_unknown`` and ``base_state_unknown`` are retryable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1] / "hooks"))  # appended: never shadow a module of the caller
import release_descent  # noqa: E402  (stdlib-only, shared with the release guard hook)

from . import release_commit, release_paths, release_publish, release_runstate, release_verify  # noqa: E402
from .release_runner import Recorder  # noqa: E402

METHODS = (("merge", "mergeCommitAllowed"), ("squash", "squashMergeAllowed"), ("rebase", "rebaseMergeAllowed"))  # in order of preference
_PR_STATE = {"MERGED": ("pr_already_merged", "the PR is merged already; run push-tag"),
             "CLOSED": ("pr_closed_unmerged", "the PR was closed without a merge")}  # any other state: pr_state_unknown


def merge_ready(rec: Recorder, plugin_root: Path, *, version: str) -> tuple[int, dict[str, Any]]:
    root = rec.cwd
    state, record = release_runstate.stored(root, version) or {}, release_commit.read_state(root) or {}
    out: dict[str, Any] = {"version": version}

    def answer(status: str, code: int, **more: Any) -> tuple[int, dict[str, Any]]:
        release_publish.redact(rec)  # the push URL the base fetch reads may carry a user and token: never in the answer
        return code, {**out, **more, "status": status, "commands": rec.as_json()}

    def refuse(reason: str, detail: str, **more: Any) -> tuple[int, dict[str, Any]]:
        return answer("refused", 1, reason=reason, detail=detail, **more)

    commit, branch = record.get("commit"), state.get("branch")
    if record.get("version") != version or not commit:
        return refuse("release_not_committed", "no release commit is recorded for this version; run commit-and-tag first")
    if state.get("on_trunk"):
        return refuse("released_on_the_trunk", "a release on the trunk has no PR to merge")
    if state.get("mode") != "standalone":
        return refuse("driven_run_never_merges", "a driven run leaves its PR to the run that started it")
    if state.get("autonomy") not in release_verify.AUTONOMOUS:
        return refuse("merge_left_to_a_person", "a guided release waits for a person to merge the PR")
    if not branch or not state.get("pr_url"):
        return refuse("event_not_recorded", "run record-event with the PR URL first")
    if rec.run("merge-branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip() != branch:  # the line merges the current branch's PR
        return refuse("head_not_on_branch", f"check out the release branch {branch} first")
    head = rec.run("merge-head", ["git", "rev-parse", "HEAD"]).stdout.strip()

    def git(*args: str) -> tuple[int, str]:
        done = rec.run("merge-git", ["git", *args])
        return done.exit, done.stdout

    if not release_descent.is_the_release(git, commit, head):
        return refuse("head_moved_since_release", f"HEAD {head[:10]} is not the release commit {commit[:10]} or its event commit")
    out.update(branch=branch, head=head)
    view = _gh_json(rec, plugin_root, "merge-pr-view", "pr", "view", state["pr_url"], "--json", "state,headRefOid,baseRefName")
    if view.get("state") != "OPEN":
        return refuse(*_PR_STATE.get(str(view.get("state")), ("pr_state_unknown", "gh could not say whether the PR is open; run merge-ready again")))
    if view.get("headRefOid") != head:
        return refuse("pr_head_not_the_release", f"the PR head on the host is {str(view.get('headRefOid'))[:10]}, not the release's {head[:10]}; "
                      "push the release branch, or restart the release if someone else pushed to it")
    base_name = state.get("base_branch") or state.get("trunk")
    if base_name and view.get("baseRefName") != base_name:  # a retargeted PR would merge into another branch than the one checked
        return refuse("pr_base_changed", f"the PR now targets {view.get('baseRefName')}, not {base_name}; restart the release")
    settings = _gh_json(rec, plugin_root, "merge-settings", "repo", "view", "--json", ",".join(name for _, name in METHODS))
    if not all(isinstance(settings.get(name), bool) for _, name in METHODS):
        return refuse("repo_settings_unknown", "gh could not read which merge methods the repository allows; run merge-ready again")
    method = next((m for m, name in METHODS if settings[name]), None)
    if method is None:
        return refuse("no_merge_method_allowed", "the repository allows no merge method; a person merges the PR")
    out["method"] = method
    if method != "merge":
        base, fetched = release_verify.fetch_base(rec, {**state, "base_branch": base_name or view.get("baseRefName")}, prefix="merge")  # the PR's own base when none is stored
        behind = rec.run("merge-behind", ["git", "merge-base", "--is-ancestor", "FETCH_HEAD", head]) if fetched.exit == 0 else None
        if behind is None or behind.exit not in (0, 1):
            why = release_publish._USERINFO.sub("***@", (fetched.stderr if behind is None else behind.stderr).strip())[:120]
            return refuse("base_state_unknown", f"could not tell whether {base} moved ({why or 'git gave no reason'}); run merge-ready again", base=base)
        if behind.exit == 1:
            return refuse("base_moved", _restart(base, version, method), base=base)
        out["base"] = base
    argv = ["gh", "pr", "merge", f"--{method}", "--match-head-commit", head, "--delete-branch"]
    return answer("ok", 0, argv=argv, line=" ".join(argv))


def _restart(base: str, version: str, method: str) -> str:
    return (f"Nothing was merged. {base} got new commits after the release branch was made, so a {method} merge now would put code into "
            f"v{version} that its changelog does not describe. Restart the release by hand: close the release PR, delete the local tag "
            f"(git tag -d v{version}; it was never pushed), switch to an up-to-date {base} and run /shipwright-changelog again.")


def _gh_json(rec: Recorder, plugin_root: Path, key: str, *args: str) -> dict[str, Any]:
    """``gh <args>`` (through the test seam) as a JSON object; unreadable, a failed call or an unusable seam is ``{}``."""
    argv = release_paths.gh(plugin_root, *args)
    if not argv:
        return {}
    done = rec.run(key, argv)
    try:
        found = json.loads(done.stdout)
    except ValueError:
        return {}
    return found if done.exit == 0 and isinstance(found, dict) else {}
