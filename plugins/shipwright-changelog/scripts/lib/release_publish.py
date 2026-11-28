"""``release.py push-tag`` after a squash or rebase merge (D110 part 2, D112; unit U3): prove the PR's merge commit, record it, retag.

After a squash or rebase merge the release commit R never reaches the base; the PR's merge commit S does (``gh pr view --json
headRefOid,mergeCommit``: H is the PR head at merge time). S is accepted only when all three hold, nothing weaker:

1. H is R or an event-only descendant of R (``release_descent``): no commit was pushed to the branch after ``record-event``;
2. S is an ancestor of the freshly fetched base: the base was not force-pushed past it;
3. the merge proof holds (``scripts/hooks/release_merge_proof``, the rule the release guard and the closing verify read): S's tree
   is H's, and S sits directly on a base H already held. Any foreign commit that landed on the base before the merge breaks it.

When 3 fails the release stops with ``foreign_commits_on_base``: the first-parent commits from ``merge-base(H, S)`` to S, minus the
PR's own (S itself and, after a rebase, the commits whose patch H carries: best-effort), with the changelog drops each one added.
Nothing is written and no tag moves; an operator decides what follows (for v0.37.0 it was addendum #1116).

When all hold: the record (``.shipwright/runtime/release_state.json``) gets ``published_commit``, ``merged_via`` and ``proof``. The tag
is moved onto S in code (``git tag -f -a``, the message names R) only while it is not on origin; a tag already on origin is never
moved (it is accepted only when it names S). A re-run with the same record gives the same answer; a record that already names
another merge commit is refused (``merge_commit_changed``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1] / "hooks"))  # appended: never shadow a module of the caller
import release_descent  # noqa: E402  (stdlib-only, shared with the release guard hook)
import release_merge_proof  # noqa: E402

from . import release_commit  # noqa: E402
from .release_runner import CmdResult, Recorder  # noqa: E402

DROPS = "CHANGELOG-unreleased.d/"
_USERINFO = re.compile(r"(?<=://)[^/\s]*@")  # the user:token part of a URL
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _sha(value: Any) -> str:
    return value if isinstance(value, str) and release_commit.SHA.fullmatch(value) else ""


def merge_facts(view: dict[str, Any]) -> tuple[str, str]:
    """``(H, S)`` from ``gh pr view --json headRefOid,mergeCommit``; ``""`` for what it did not report."""
    merge = view.get("mergeCommit")
    return _sha(view.get("headRefOid")), _sha(merge.get("oid") if isinstance(merge, dict) else None)


def _method(git: release_descent.Git, merged: str, head: str) -> tuple[str, str]:
    """``(merged_via, base_before)`` read from S's shape: two parents is a merge commit; one parent that H holds is a squash; else a
    rebase whose replayed chain is as long as the PR's. What fits none is called a squash on S's parent, which the proof then refuses."""
    found = release_merge_proof.parents(git, merged) or []
    if len(found) == 2:
        return "merge", found[0]
    first = found[0] if found else ""
    if not first or git("merge-base", "--is-ancestor", first, head)[0] == 0:
        return "squash", first
    fork = git("merge-base", head, merged)[1].strip()
    count = git("rev-list", "--count", "--first-parent", f"{fork}..{head}")[1].strip() if fork else ""
    code, base = git("rev-parse", "--verify", "-q", f"{merged}~{count}^{{commit}}") if count.isdigit() else (1, "")
    base = base.strip()
    cherry = git("cherry", head, merged, base) if code == 0 and int(count) > 1 else (1, "")
    replays = [line for line in cherry[1].splitlines() if line.strip()] if cherry[0] == 0 else []
    if replays and all(line.startswith("- ") for line in replays):  # every commit on top of the base is a PR commit replayed
        return "rebase", base
    return "squash", first


def foreign_commits(git: release_descent.Git, head: str, merged: str) -> list[dict[str, Any]]:
    """The first-parent commits from ``merge-base(H, S)`` to S that are not the PR's own, oldest first, with the drops each added."""
    fork = git("merge-base", head, merged)[1].strip()
    if not fork:
        return []
    chain = git("rev-list", "--reverse", "--first-parent", f"{fork}..{merged}")[1].split()
    replayed = {line[2:].strip() for line in git("cherry", head, merged, fork)[1].splitlines() if line.startswith("- ")}
    out = []
    for commit in (c for c in chain if c != merged and c not in replayed):
        subject = _CONTROL.sub(" ", git("log", "-1", "--format=%s", commit)[1].strip())[:80]  # another person's words: data, kept short
        added = git("diff-tree", "--no-commit-id", "--name-only", "-r", "--diff-filter=A", "-m", "--first-parent", commit, "--", DROPS)[1]
        out.append({"commit": commit, "subject": subject, "drops": sorted({p.strip() for p in added.splitlines() if p.strip()})})
    return out


def redact(rec: Recorder, since: int = 0) -> None:
    """Drop the user:token part of a URL from what the commands since ``since`` report (the JSON answer carries them)."""
    for i in range(since, len(rec.results)):
        r = rec.results[i]
        rec.results[i] = CmdResult(r.key, tuple(_USERINFO.sub("***@", a) for a in r.argv), r.exit, _USERINFO.sub("***@", r.stdout),
                                   _USERINFO.sub("***@", r.stderr))


def _remote(rec: Recorder, command: list[str], after: list[str]) -> tuple[int, str]:
    """A git call that asks origin, at the push URL (where the push goes, as the closing verify asks): no prompt, no URL in the answer."""
    start = len(rec.results)
    url = rec.run("push-git", ["git", "remote", "get-url", "--push", "origin"]).stdout.strip() or "origin"
    done = rec.run("push-git", ["git", "-c", "credential.interactive=never", *command, "--end-of-options", url, *after],
                   env=release_descent.NO_PROMPT, timeout=120)
    redact(rec, start)
    return done.exit, done.stdout


def publish(rec: Recorder, record: dict[str, Any], *, tag: str, base_branch: str, view: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """``("ok", fields)`` after the proof was written and the local tag names S, else ``(reason, fields)``; never pushes.
    ``base_branch`` is the PR's base branch: fetched here, after ``gh pr view`` reported the merge, so S is in it when it is on origin."""
    def git(*args: str) -> tuple[int, str]:
        done = rec.run("push-git", ["git", *args])
        return done.exit, done.stdout

    release, (head, merged) = record["commit"], merge_facts(view)
    if not head or not merged:
        return "merge_commit_unknown", {"detail": "the PR is merged, but gh did not report its head and merge commit; nothing is pushed"}
    facts = {"pr_head": head, "merge_commit": merged}
    if view.get("baseRefName") and view["baseRefName"] != base_branch:  # the PR was retargeted: the proof would read the wrong branch
        return "pr_base_changed", {**facts, "detail": f"the PR's base is {view['baseRefName']}, the release recorded {base_branch}; nothing is pushed"}
    prior = release_merge_proof.claimed(record)
    if prior and prior != merged:  # an earlier run recorded another merge commit: no rule says which one is the release's
        return "merge_commit_changed", {**facts, "recorded": prior, "detail": f"the record names the merge commit {prior[:10]}, gh now "
                                        f"reports {merged[:10]}; nothing is pushed"}
    if not release_descent.is_the_release(git, release, head):
        return "pr_head_not_the_release", {**facts, "detail": "the PR head at the merge is not the release commit or its event commit: "
                                                              "something was pushed to the branch after the release; nothing is pushed"}
    if _remote(rec, ["fetch", "--quiet"], [base_branch])[0] != 0:
        return "merge_state_unknown", {**facts, "detail": f"origin's {base_branch} could not be fetched; run push-tag again"}
    fetched = git("rev-parse", "--verify", "-q", "FETCH_HEAD^{commit}")[1].strip()
    if not fetched or git("merge-base", "--is-ancestor", merged, fetched)[0] != 0:
        return "merge_commit_not_on_base", {**facts, "detail": "the PR's merge commit is not on the base fetched from origin; nothing is pushed"}
    via, base = _method(git, merged, head)
    claim = {**record, "published_commit": merged, "merged_via": via,
             "proof": {"pr_head": head, "tree": git("rev-parse", "--verify", "-q", f"{head}^{{tree}}")[1].strip(), "base_before": base}}
    if release_merge_proof.proven(git, claim) != merged:
        found = foreign_commits(git, head, merged)
        named = "; ".join(f"{c['commit'][:10]} {c['subject']}" + (f" (drops: {', '.join(c['drops'])})" if c["drops"] else "") for c in found)
        trees = {"tree_pr_head": claim["proof"]["tree"], "tree_merge_commit": git("rev-parse", "--verify", "-q", f"{merged}^{{tree}}")[1].strip()}
        why = f"commits landed on the base before the merge and are in it: {named}" if found else \
            "the merge commit's content differs from the PR head (a merge queue or a conflict resolved on the web changes it)" \
            if trees["tree_pr_head"] != trees["tree_merge_commit"] else \
            "the merge commit holds the PR head's content but is not a squash, merge or rebase of it onto a base the PR held"
        if found and not any(c["drops"] for c in found):
            why += " (none of them added a changelog drop: restarting the release from the current base takes them in)"
        return "foreign_commits_on_base", {**facts, **trees, "merged_via": via, "base_before": base, "foreign_commits": found,
                                           "detail": why + ". Their changelog entries are not in this release. Nothing is tagged or written; "
                                                           "an operator decides what follows"}
    remote = _remote(rec, ["ls-remote", "--tags"], [f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"])
    if remote[0] != 0:
        return "merge_state_unknown", {**facts, "detail": "origin could not be asked whether it holds the tag; run push-tag again"}
    shas = {line.split()[1]: line.split()[0] for line in remote[1].splitlines() if len(line.split()) == 2}
    pushed = shas.get(f"refs/tags/{tag}^{{}}") or shas.get(f"refs/tags/{tag}")
    if pushed and pushed != merged:  # never move a tag that is already out
        return "tag_on_origin_not_the_merge_commit", {**facts, "tag_commit": pushed,
                                                      "detail": f"{tag} on origin names {pushed[:10]}, not the merge commit; it is never moved"}
    release_commit.write_state(rec.cwd, claim)  # first: a tag on S with a record that does not name S would be denied by the guard
    if pushed and git("rev-parse", "--verify", "-q", f"refs/tags/{tag}")[1].strip() != shas.get(f"refs/tags/{tag}"):
        # origin already holds a tag on S, made elsewhere: take its exact object, or the printed push would be refused as "already exists"
        if _remote(rec, ["fetch", "--quiet", "--force", "--no-tags"], [f"refs/tags/{tag}:refs/tags/{tag}"])[0] != 0:
            return "retag_failed", {**facts, "detail": f"{tag} on origin names the merge commit but could not be fetched; run push-tag again"}
    retag = git("rev-parse", "--verify", "-q", f"refs/tags/{tag}^{{commit}}")[1].strip() != merged
    if retag and git("tag", "-f", "-a", tag, "-m", f"Release {tag} ({via} merge of the release commit {release})", merged)[0] != 0:
        return "retag_failed", {**facts, "detail": f"git tag could not move {tag} onto the merge commit; run push-tag again"}
    return "ok", {**facts, "merged_via": via, "retagged": retag}
