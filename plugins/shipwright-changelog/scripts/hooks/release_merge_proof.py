"""The one rule "this commit is the release, or its proven merge commit" shared by the release guard hook and the closing verify
(D110 part 1, unit U2). Stdlib only, next to ``release_descent`` whose rule it extends.

After a squash or rebase merge the release commit R never reaches the base: the PR's merge commit S does. The release record
(``.shipwright/runtime/release_state.json``) keeps ``commit = R`` and may carry three optional fields: ``published_commit = S``,
``merged_via`` (``merge``, ``squash`` or ``rebase``) and ``proof = {pr_head, tree, base_before}``. ``release.py push-tag`` writes them
after it proved the merge (unit U3); until then nothing writes them and a record without them is judged exactly as before.

A judged commit passes when it is the release (``release_descent.is_the_release``: R, or an event-only descendant of R), or when it
is ``published_commit`` and the proof still holds in this repository:

- ``proof.pr_head`` is the release (R or an event-only descendant of R), and
- ``proof.tree`` is both the tree of ``proof.pr_head`` and the tree of ``published_commit``, and
- ``proof.base_before`` (the base just before the merge) is an ancestor of ``published_commit`` (S grows from that base).

So S carries exactly the audited content of the release. A hand-edited record cannot approve any other commit: a different S has
a different tree, and a ``proof`` pointing at another head is not the release. A malformed or partial set of the new fields is no
claim at all (the release-descent rule alone).

Trust boundary: this rule proves content and that S grows from the recorded base, not that S is on the base on origin. That is proven by the writer (U3: S is an ancestor of
the freshly fetched base) and checked again by the closing verify's PR check (S on the base on origin). The guard cannot ask the
remote (D90), so a commit with exactly the release's tree that is not on the base passes the guard; its content is the audited
release, so the worst case is a tag off the trunk, which the closing verify then fails. ``base_before`` means what U3's writer
makes it mean (the fetched base tip the merge was made on); a hand-edited record can name any ancestor of S there, so the
guard's protection rests on the two tree checks, never on ``base_before``. A merge commit or a squash made after the
base moved has another tree and is refused here; U3 keeps a merge commit on R and stops on foreign commits (D112).

The caller supplies ``git(*args) -> (exit_code, stdout)`` as for ``release_descent``. Loaded by ``release_guard.py`` from its own
directory and by ``lib/release_verify.py`` by path.
"""

from __future__ import annotations

import re
from typing import Any

import release_descent

MERGED_VIA = ("merge", "squash", "rebase")
PROOF_KEYS = ("pr_head", "tree", "base_before")
_SHA = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")


def _sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def claimed(record: Any) -> str | None:
    """The record's ``published_commit`` when it and every field that goes with it are well formed, else ``None``. No git call."""
    if not isinstance(record, dict) or not _sha(record.get("commit")):
        return None
    published, proof = record.get("published_commit"), record.get("proof")
    if not _sha(published) or record.get("merged_via") not in MERGED_VIA or not isinstance(proof, dict):
        return None
    return published if all(_sha(proof.get(key)) for key in PROOF_KEYS) else None


def _tree(git: release_descent.Git, commit: str) -> str:
    code, out = git("rev-parse", "--verify", "-q", f"{commit}^{{tree}}")
    return out.strip() if code == 0 else ""


def proven(git: release_descent.Git, record: Any) -> str | None:
    """``published_commit`` when the record claims one and its proof holds in this repository, else ``None``.
    Asks git only when the record claims a published commit, so a record without the new fields costs no git call."""
    published = claimed(record)
    if not published:
        return None
    proof = record["proof"]
    if not release_descent.is_the_release(git, record["commit"], proof["pr_head"]):
        return None
    tree = proof["tree"]
    if _tree(git, proof["pr_head"]) != tree or _tree(git, published) != tree:
        return None
    return published if git("merge-base", "--is-ancestor", proof["base_before"], published)[0] == 0 else None  # S grows from the recorded base


def accepts(git: release_descent.Git, record: Any, judged: str) -> bool:
    """``judged`` is the release (the record's commit or an event-only descendant of it), or the record's proven published commit."""
    if not judged or not isinstance(record, dict) or not _sha(record.get("commit")):
        return False
    if release_descent.is_the_release(git, record["commit"], judged):
        return True
    return judged == claimed(record) and proven(git, record) == judged
