"""Which tree was a measurement taken in? (iterate-2026-07-28-grade-snapshot-lineage)

A Control Grade is a property of a **tree state**, not of a repository in the
abstract. Every iterate regenerates compliance inside its own worktree and
commits the resulting ``grade_snapshot`` into its PR; ``shipwright_events.jsonl``
merges by union, so every branch's snapshots land in one file on ``main``. Without
attribution the WebUI Ship's-Log plots a mixture of divergent trees as if it were
one project's trend (observed: ``A 92.5 -> F 49.0 -> A 91.5 -> B 87.4 -> C 79.9``
in five days). This module resolves the three facts that tell them apart.

Why not ``commit``: at finalize time the regen runs BEFORE the F6 commit, so HEAD
is still the *previous* commit and would mislabel the snapshot. ``base`` — the
merge-base with the default branch — has no such defect: it names a real,
already-existing commit that the measured tree extends, true whether or not F6
has run.

**What ``base`` guarantees.** A common ancestor *reachable from* the default
branch. That is git's guarantee and nothing stronger — it is NOT promised to sit
on the default branch's first-parent chain (merge commits and criss-cross history
break that). Consumers ordering snapshots along the default branch must use
general ancestry / topological position, not first-parent indexing.

**Placement (ADR-045).** Top-level under ``shared/scripts/``, deliberately *not*
under ``lib/`` — the same seam as ``tests_block.py``. The compliance emitter that
calls this lives in the plugin's own ``scripts.lib`` namespace, so a shared
``lib.X`` import would shadow it. This module is stdlib-only and carries its own
small git runner rather than reusing ``source_state_git._git``: that name is
private, and every transitive import added on this lazily-imported cross-plugin
path is another chance to bind the wrong ``lib``. The ~15 duplicated lines of
``subprocess.run`` are a deliberate price for an import that cannot go wrong.

**Nothing here raises.** Attribution is best-effort metadata on a producer that
must never fail because of it; every git failure degrades to ``None``.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Bounded so a wedged git can never stall a compliance regen.
_GIT_TIMEOUT_SECONDS = 5

#: Tried in order when ``origin/HEAD`` is absent — and only ever ACCEPTED when
#: the ref actually resolves. Falling back to the literal string ``main`` would
#: label a regen on a ``master`` repo's default branch as ``"branch"``.
_DEFAULT_CANDIDATES = (
    "origin/main", "origin/master", "origin/trunk", "main", "master", "trunk",
)

#: Object names are validated as hex rather than assumed to be 40-char SHA-1, so
#: a SHA-256 repository is accepted while garbage never reaches the durable log.
_OBJECT_NAME = re.compile(r"^[0-9a-f]{7,64}$")

#: Closed vocabulary. ``"unknown"`` is a real value, emitted when the producer
#: tried and could not tell — distinct from the field being ABSENT, which means
#: the event predates attribution entirely.
LINEAGE_MAIN = "main"
LINEAGE_BRANCH = "branch"
LINEAGE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class TreeLineage:
    """``lineage`` is always set; ``branch``/``base`` are ``None`` when unresolved."""

    lineage: str
    branch: str | None
    base: str | None


def _git(root: Path, *args: str) -> str | None:
    """git stdout (stripped), or ``None`` on any failure.

    Always ``git -C <root>``: the producer runs inside a worktree whose tree is
    not the shell's cwd, so relying on process-cwd would measure the wrong repo.
    """
    code, out = _git_status(root, *args)
    if code != 0 or out is None:
        return None
    return out.strip() or None


def _git_status(root: Path, *args: str) -> tuple[int | None, str | None]:
    """``(returncode, stdout)``; ``(None, None)`` when git could not run at all.

    The exit code is exposed because ``merge-base --is-ancestor`` answers with
    it: ``0`` ancestor, ``1`` genuinely not an ancestor, anything else "could not
    tell". Collapsing that third case into ``1`` would silently relabel
    main-lineage trees as branches.

    ``errors="replace"`` is load-bearing, not decoration: git ref names and
    localized diagnostics are byte strings that need not be valid UTF-8, and a
    ``UnicodeDecodeError`` is a ``ValueError`` — neither ``OSError`` nor
    ``SubprocessError`` — so strict decoding would raise straight through the
    "nothing here raises" contract (external code review, edge-case/low).
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS, check=False, shell=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        # ValueError covers UnicodeDecodeError, which ``errors="replace"`` should
        # already prevent — kept so the contract survives anyone later tightening
        # the decode, rather than resting on one keyword argument.
        return None, None
    return proc.returncode, proc.stdout


def _resolve_default_branch(root: Path) -> str | None:
    """The repository's default branch, or ``None`` if none can be established.

    ``origin/HEAD`` is authoritative and wins whenever its target resolves — that
    is what stops a stray local branch named ``main`` from hijacking a ``master``
    repository. Only if it is absent do we probe candidates, and a candidate is
    accepted only when the ref exists.
    """
    head = _git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        name = head[len("origin/"):] if head.startswith("origin/") else head
        if name and _rev_parse(root, f"origin/{name}"):
            return name
    for candidate in _DEFAULT_CANDIDATES:
        if _rev_parse(root, candidate):
            return candidate[len("origin/"):] if candidate.startswith("origin/") else candidate
    return None


def _rev_parse(root: Path, ref: str) -> str | None:
    """The object ``ref`` names, or ``None`` when it does not resolve."""
    return _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")


def _default_ref(root: Path, default_branch: str) -> str | None:
    """Prefer the remote-tracking ref; fall back to the local branch."""
    for ref in (f"origin/{default_branch}", default_branch):
        if _rev_parse(root, ref):
            return ref
    return None


def resolve_tree_lineage(project_root: Path | str) -> TreeLineage:
    """Resolve which tree ``project_root`` is, for stamping onto an event.

    ``lineage`` is ``"main"`` when the measured tree contains nothing that is not
    already on the default branch — either because the checked-out branch IS the
    default (covering a local default that is ahead of its remote), or because
    HEAD is an ancestor of the default ref (covering a detached HEAD at any
    default-branch commit, not merely at the tip). Otherwise ``"branch"``, and
    ``"unknown"`` when git cannot answer.
    """
    root = Path(project_root)

    head = _git(root, "rev-parse", "HEAD")
    if head is None:
        # No git, not a repo, or a repo with no commits: nothing is knowable.
        return TreeLineage(LINEAGE_UNKNOWN, None, None)

    name = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    branch = None if name in (None, "HEAD") else name

    default_branch = _resolve_default_branch(root)
    if default_branch is None:
        # A branch name is still a fact worth reporting even when we cannot say
        # what it is relative to.
        return TreeLineage(LINEAGE_UNKNOWN, branch, None)

    ref = _default_ref(root, default_branch)
    if ref is None:  # pragma: no cover - _resolve_default_branch already proved one resolves
        return TreeLineage(LINEAGE_UNKNOWN, branch, None)

    base = _git(root, "merge-base", "HEAD", ref)

    if branch == default_branch:
        lineage = LINEAGE_MAIN
    else:
        code, _ = _git_status(root, "merge-base", "--is-ancestor", "HEAD", ref)
        if code == 0:
            lineage = LINEAGE_MAIN
        elif code == 1:
            lineage = LINEAGE_BRANCH        # genuinely carries unmerged commits
        else:
            # "Could not tell" — a shallow clone with truncated history, an
            # unreadable object. Whether that is still an answer depends on what
            # else we know: a NAMED non-default branch is a branch on the
            # strength of its name alone, but a detached HEAD with no ancestry
            # answer is genuinely unknowable, and guessing "branch" there would
            # file a main-lineage measurement under the wrong subject.
            lineage = LINEAGE_BRANCH if branch else LINEAGE_UNKNOWN

    return TreeLineage(lineage, branch, base)


def lineage_fields(lineage: TreeLineage) -> dict[str, str]:
    """Project a :class:`TreeLineage` onto the event keys to merge into a snapshot.

    ``lineage`` is always present; ``branch``/``base`` appear only when resolved,
    so a partial answer still carries what it knows instead of discarding all
    three. An implausible object name is dropped rather than stamped.
    """
    fields: dict[str, str] = {"lineage": lineage.lineage}
    if lineage.branch:
        fields["branch"] = lineage.branch
    if lineage.base and _OBJECT_NAME.match(lineage.base):
        fields["base"] = lineage.base
    return fields


__all__ = [
    "LINEAGE_BRANCH",
    "LINEAGE_MAIN",
    "LINEAGE_UNKNOWN",
    "TreeLineage",
    "lineage_fields",
    "resolve_tree_lineage",
]
