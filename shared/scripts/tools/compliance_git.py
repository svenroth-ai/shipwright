#!/usr/bin/env python3
"""The three git/index primitives both compliance deliveries need.

Sixth module of the compliance-evidence refresh
(iterate-2026-07-31-derived-docs-at-release). Its own file because BOTH
deliveries use these — :mod:`tools.compliance_delivery` for the on-demand pull
request and :mod:`tools.refresh_compliance_docs` for the release path and
``--restore`` — and putting them in either would make the other import its
sibling's private half.

Each carries a defect it was taught by:

* :func:`staged_difference` returns ``None`` when git could not answer, because
  returning ``[]`` made a failed ``git add`` read as "nothing differed" — green,
  having shipped nothing.
* :func:`restore_to_head` ASKS whether ``HEAD`` carries a path instead of
  inferring it from a failed checkout, because inferring deleted committed
  evidence when a file was merely held open.
* :func:`write_back` exists because the generator's output is not what ships —
  the STAMPED bytes are — and a delivery that stages whatever is on disk commits
  the unstamped copy while reporting otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

# UNCONDITIONAL — see the note in `tools/compliance_refresh_produce.py` (ADR-045).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.compliance_refresh import REFRESH_SET  # noqa: E402
from tools.compliance_refresh_produce import git  # noqa: E402

__all__ = ["restore_to_head", "staged_difference", "write_back"]


def staged_difference(root: Path, rels: list[str]) -> list[str] | None:
    """Stage ``rels`` and return the subset that actually DIFFERED from ``HEAD``.

    Reporting "every refresh path that exists" is the most misleading possible
    answer to "did anything change?", so the caller gets the real subset.

    **``None`` means git could not answer, and that is not ``[]``.** An empty list
    is a fact — the committed documents already match. An empty list returned
    because ``git add`` failed is the opposite, and the two arrived identically
    until this returned ``None``: the delivery read the failure as "nothing
    differed", reported ``noop``, and exited 0 having shipped nothing. That is the
    precise failure class this whole change exists to remove, so it must not live
    inside it (ADR-052's None-vs-``[]`` convention).
    """
    present = [rel for rel in sorted(rels) if (root / rel).is_file()]
    if not present:
        return []
    if git(root, "add", "--", *present).returncode != 0:
        return None
    listed = git(root, "diff", "--cached", "--name-only", "--", *present)
    if listed.returncode != 0:
        return None
    return sorted(line.strip() for line in (listed.stdout or "").splitlines()
                  if line.strip())


def restore_to_head(root: Path) -> tuple[list[str], list[str]]:
    """Reset the seven to ``HEAD``. Returns ``(moved, unresolved)``.

    Per path and via ``checkout`` (not ``restore``): ``checkout HEAD -- a b c`` is
    all-or-nothing, so one path unknown to ``HEAD`` would abort the whole call and
    silently leave the others dirty. ``checkout`` also resets the INDEX, so a copy
    some producer already staged is unstaged too.

    ``moved`` is what actually CHANGED, compared before and after — not every path
    whose checkout exited 0, which is every path present in ``HEAD`` whether it was
    dirty or not (Stage-2 code review, low). ``unresolved`` names a path the
    producer CREATED that ``HEAD`` does not carry: its checkout necessarily fails,
    and it is deleted rather than silently left on disk, because leaving it is
    exactly what hands the next ``git add`` the content this call exists to remove.
    """
    moved: list[str] = []
    unresolved: list[str] = []
    for rel in sorted(REFRESH_SET):
        path = root / rel
        before = path.read_bytes() if path.is_file() else None
        # ASK whether HEAD carries it; never INFER it from a failed checkout.
        # Reading every non-zero exit as "unknown to HEAD" meant a file held open
        # by an editor, or an `index.lock` race with a concurrent hook, deleted a
        # COMMITTED evidence document and reported it as restored, exit 0
        # (Stage-3 doubt D3). On Windows both are ordinary.
        in_head = git(root, "cat-file", "-e", f"HEAD:{rel}").returncode == 0
        checked_out = git(root, "checkout", "HEAD", "--", rel).returncode == 0
        if checked_out:
            after = path.read_bytes() if path.is_file() else None
            if after != before:
                moved.append(rel)
            continue
        if in_head:
            # HEAD has it and the checkout still failed: something is holding the
            # path. Say so; do not "resolve" it by deleting the file.
            unresolved.append(rel)
            continue
        # Genuinely absent from HEAD — the producer created it. Unstage and remove,
        # because leaving it is what hands the next `git add` the content this call
        # exists to remove.
        git(root, "rm", "--cached", "--force", "--quiet", "--", rel)
        if not path.is_file():
            continue
        try:
            path.unlink()
            moved.append(rel)
        except OSError:
            unresolved.append(rel)
    return moved, unresolved


def write_back(root: Path, payload: dict[str, bytes]) -> None:
    """Put the delivered bytes on disk. Both deliveries need this, for one reason.

    ``produce`` returns STAMPED bytes — the generator's output is not what ships.
    A delivery that stages whatever the generator happened to leave on disk
    commits the unstamped copy while `result["stamped"]` says otherwise, which is
    worse than not stamping at all: the run reports a fixed point the documents do
    not carry (Stage-1 spec review, HIGH-1).
    """
    for rel, blob in sorted(payload.items()):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(blob)
