"""Shared commit-resolution primitive for the "rollout-transition grace"
pattern: asking a repo's OWN git history whether a candidate commit already
existed at-or-before some gate's own rollout instant.

**Scope, deliberately narrow.** This module owns exactly the ~20 lines every
rollout-grace gate family needed byte-for-byte identically — the shallow-clone
guard, the ``rev-list --before`` lookup, the committer-epoch re-verification,
and the corroborated-trunk-ancestry trust anchor (`trg-4380c61a`) — and
nothing else. It does NOT own, and never will: which epoch a family uses, what
a resolved commit's content means, or how/whether a family caches its own
results. Each of :mod:`_project_gate_rollout` (FR-01.02 #5/#10,
`trg-9583d3a8`) and :mod:`_layer_coverage_rollout`
(``check_binding_completeness``, `trg-aedcfe7b`) stays a standalone module
with its OWN ``GATE_ROLLOUT_AT_EPOCH`` and its OWN cache (their result shapes
differ — a bare SHA vs. a built requirement manifest — so a shared cache would
have to be keyed on more than ``(root, commit)`` or store a lossy union type)
and now calls :func:`resolve_rollout_commit` here, passing ``epoch=`` as a
keyword so the call site never reads as "the" rollout instant.

**Why extracted now, and why only this much.** External plan review (glm,
low) on `iterate-2026-09-12-project-gate-rollout-transition` flagged this as
a THIRD near-identical copy of the same resolution logic and asked for a
shared primitive — `iterate-2026-09-20-shared-rollout-commit-resolver`. The
P3.3 ADR's own "Out of Scope" precedent (see :mod:`_project_gate_rollout`'s
module docstring) still holds for everything ABOVE this line: each gate
family keeps its own rollout INSTANT, its own module identity, and decides
for itself when and how to call this. Only the mechanical git-plumbing moved;
no family's rollout instant, caching strategy, or trust-anchor behaviour
changed.

**Fail-open direction, unchanged from the precedent this replaces:** every
failure WITHHOLDS grace, never grants a false one. A shallow clone, an absent
rollout commit, or any git failure all degrade to ``None`` — the worst
outcome is an unexplained HARD block identical to today's pre-existing
behaviour, never a silently weakened gate. See either family module's own
docstring for the full trust-anchor rationale (`trg-4380c61a`); it is not
repeated here since it is a property of the algorithm, not of any one
family's epoch.
"""

from __future__ import annotations

from pathlib import Path

from .git_helpers import _GIT_TIMEOUT_SECONDS, _branch_base_commit, _run_git


def is_shallow(project_root: Path) -> bool:
    """Best-effort: True unless git affirmatively says this is a full clone.

    Fails toward "shallow" (no grace) on any ambiguity — a shallow clone's
    ``rev-list --before`` result is untrustworthy (it can return a real,
    present commit that is simply the oldest one the clone happens to have,
    not "the state at that instant"), and granting grace on a false negative
    here is the wrong direction for an optional leniency."""
    rc, out, _ = _run_git(project_root, "rev-parse", "--is-shallow-repository",
                          timeout=_GIT_TIMEOUT_SECONDS)
    return not (rc == 0 and out.strip() == "false")


def resolve_head_sha(project_root: Path, ref: str) -> str | None:
    """``ref`` resolved to a concrete SHA, or ``None`` on any failure.

    Callers typically pass the literal string ``"HEAD"`` and resolve it
    immediately so every cache they keep is keyed by an immutable value,
    never a symbolic name that can silently point somewhere else on the
    next call within the same process."""
    rc, out, _ = _run_git(project_root, "rev-parse", ref, timeout=_GIT_TIMEOUT_SECONDS)
    if rc != 0 or not out.strip():
        return None
    return out.strip()


def resolve_rollout_commit(project_root: Path, commit_hash: str, *, epoch: int) -> str | None:
    """The calling project's own commit at-or-before ``epoch``, reachable
    from ``commit_hash`` AND an ancestor of the project's own corroborated
    trunk boundary, or ``None`` when no such commit exists: a repo born
    entirely after ``epoch``, a shallow clone, an uncorroborated/absent trunk
    anchor, or any git failure.

    Verifies the resolved commit's OWN committer time in Python rather than
    trusting git's ``--before`` parse alone (a malformed cutoff silently
    resolves to "now" — see either caller's module docstring), and requires
    the candidate to be an ancestor of (or equal to) the project's own
    corroborated trunk boundary (``git_helpers._branch_base_commit``) —
    `trg-4380c61a`: a committer-date claim alone is forgeable by whoever
    controls ``commit_hash`` (typically an open PR's own HEAD), so a
    self-authored, unmerged commit on that branch carrying a backdated
    ``GIT_COMMITTER_DATE`` must never qualify merely because it satisfies
    every check that only reads its own reachable history.

    ``epoch`` is caller-supplied and unvalidated by the type hint alone — a
    malformed value (a non-int, e.g. an empty string) would otherwise either
    reopen the exact approxidate "unparseable input means now" hazard the
    module docstring warns about (via ``f"--before={epoch}"``) or raise
    ``TypeError`` out of a function every caller treats as never-raising.
    Rejected up front, same fail-closed direction as every other branch
    here."""
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        return None
    if not commit_hash or is_shallow(project_root):
        return None
    rc, sha, _ = _run_git(
        project_root, "rev-list", "-1", f"--before={epoch}", commit_hash,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if rc != 0 or not sha.strip():
        return None
    sha = sha.strip()
    rc2, ts, _ = _run_git(project_root, "show", "-s", "--format=%ct", sha,
                          timeout=_GIT_TIMEOUT_SECONDS)
    if rc2 != 0 or not ts.strip():
        return None
    try:
        committer_epoch = int(ts.strip())
    except ValueError:
        return None
    if committer_epoch > epoch:
        return None  # git's answer postdates our cutoff — refuse rather than trust it

    base = _branch_base_commit(project_root, commit_hash)
    if base is None:
        return None  # no corroborated trunk boundary — an unverifiable ancestry claim is not grace
    rc3, count_out, _ = _run_git(
        project_root, "rev-list", "--count", f"{base}..{sha}", timeout=_GIT_TIMEOUT_SECONDS,
    )
    if not (rc3 == 0 and count_out.strip() == "0"):
        return None  # sha is not reachable from the trusted trunk boundary — refuse
    return sha


__all__ = ["is_shallow", "resolve_head_sha", "resolve_rollout_commit"]
