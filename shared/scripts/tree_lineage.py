"""Which tree was a measurement taken in?
(iterate-2026-07-28-grade-snapshot-lineage, corrected by …-honest-subject)

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

**What ``base`` guarantees:** a common ancestor *reachable from* the default
branch, nothing stronger — not first-parent, and on the main-lineage path it
equals HEAD. Consumer rules: ``docs/hooks-and-pipeline.md``.

**Placement (ADR-045).** Top-level under ``shared/scripts/``, deliberately *not*
under ``lib/`` — the same seam as ``tests_block.py``. The compliance emitter that
calls this lives in the plugin's own ``scripts.lib`` namespace, so a shared
``lib.X`` import would shadow it. This module is stdlib-only and carries its own
git runner rather than reusing ``source_state_git``'s private one: every
transitive import on this lazily-imported cross-plugin path is another chance to
bind the wrong ``lib``, so the duplication buys an import that cannot go wrong.

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

#: Ref names are untrusted external data crossing a repo boundary onto a durable
#: artifact. git imposes no length limit of its own worth relying on here.
_BRANCH_MAX = 255

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

    ``lineage`` is ``"main"`` only when the checked-out branch IS the default
    branch (which also covers a local default ahead of its remote), or — for a
    **detached** HEAD, which has no name to reason from — when HEAD is an
    ancestor of the default ref. A named non-default branch is always
    ``"branch"``, whatever its ancestry: it is a branch by name, and the working
    tree it carries is not on the default branch's timeline even when its
    commits happen to be. ``"unknown"`` when git cannot answer.
    """
    try:
        root = Path(project_root)
    except (TypeError, ValueError):
        # The one statement that could raise past the "nothing here raises"
        # contract; direct callers have no outer handler (internal code review).
        return TreeLineage(LINEAGE_UNKNOWN, None, None)

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
    elif branch is not None:
        # A NAMED non-default branch is a branch, full stop — ancestry is not
        # consulted. It used to be, and that was the defect: an iterate worktree
        # is created at the fork point and the snapshot is emitted at F5b,
        # BEFORE the only mandated commit, so HEAD was still the fork point and
        # ancestry answered "main" over a working tree holding the entire
        # uncommitted change set. That stamped the very phantom point this
        # attribution exists to expose, and stamped it as authoritative.
        # Ancestry was only ever needed for a detached HEAD, which has no name
        # to reason from (internal code review, correctness/high).
        lineage = LINEAGE_BRANCH
    else:
        code, _ = _git_status(root, "merge-base", "--is-ancestor", "HEAD", ref)
        if code == 0:
            lineage = LINEAGE_MAIN
        elif code == 1:
            lineage = LINEAGE_BRANCH        # genuinely carries unmerged commits
        else:
            # Detached AND ancestry is unobtainable (shallow clone, unreadable
            # object): there is no name to fall back on, so this is genuinely
            # unknowable and guessing would file a measurement under the wrong
            # subject.
            lineage = LINEAGE_UNKNOWN

    return TreeLineage(lineage, branch, base)


def lineage_fields(lineage: TreeLineage) -> dict[str, object]:
    """Project a :class:`TreeLineage` onto the event keys to merge into a snapshot.

    ``lineage`` is always present; the rest appear only when resolved, so a
    partial answer still carries what it knows instead of discarding everything.

    Both string fields are bounded before they are stamped, because this lands on
    a git-tracked, cross-repo-read, append-only artifact that cannot honestly be
    rewritten later: an implausible object name is dropped, and a branch name is
    dropped if it exceeds ``_BRANCH_MAX`` or carries control characters. Neither
    is reachable through the producers today — git's own ref grammar forbids the
    control characters — but "the writer happens not to emit it" is not a bound
    (internal code review, security/low).
    """
    fields: dict[str, object] = {"lineage": lineage.lineage}
    if lineage.branch and _is_stampable_branch(lineage.branch):
        fields["branch"] = lineage.branch
    if lineage.base and _OBJECT_NAME.match(lineage.base):
        fields["base"] = lineage.base
    return fields


def _is_stampable_branch(name: str) -> bool:
    """A ref name short enough and clean enough to put on the durable log."""
    return len(name) <= _BRANCH_MAX and not any(ord(c) < 0x20 or ord(c) == 0x7F for c in name)


__all__ = [
    "LINEAGE_BRANCH",
    "LINEAGE_MAIN",
    "LINEAGE_UNKNOWN",
    "TreeLineage",
    "lineage_fields",
    "resolve_tree_lineage",
]
