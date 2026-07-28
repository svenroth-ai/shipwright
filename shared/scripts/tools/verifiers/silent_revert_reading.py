"""How ``check_no_silent_revert`` reads git and compares text.

The primitives only — reading a path at a ref, telling absence apart from
failure, resolving which ref "the default branch" means, and turning a diff into
paired hunks. The policy that decides what counts as a loss lives next door in
:mod:`silent_revert_filters`; the detector itself in :mod:`silent_revert`.

Split out because both of those grew past the repo's 300-line source cap, so the
seam is the cap's doing rather than a design claim — but it is a real seam:
everything here is a question about the repository, nothing here decides whether
a finding survives.
"""

from __future__ import annotations

from pathlib import Path

from .git_helpers import _run_git


def significant_line(line: str) -> bool:
    """Whether a line is worth comparing at all — formatting churn is not lost work.

    One definition, used both when reading a file at a ref and when reading the
    two sides of a hunk, so "the same line" cannot come to mean two things.
    """
    return bool(line.strip())


def file_lines(project_root: Path, ref: str, path: str) -> set[str] | None:
    """The significant lines of ``path`` at ``ref``; ``None`` if it cannot be read.

    ``None`` is deliberately ambiguous between "absent" and "unreadable" for the
    detector's own uses, where both mean "do not compare". Where the difference
    decides whether a finding is suppressed, use :func:`tip_state` instead.
    """
    rc, out, _ = _run_git(project_root, "show", f"{ref}:{path}")
    if rc != 0:
        return None
    return {line.strip() for line in out.splitlines() if significant_line(line)}


def tip_state(project_root: Path, ref: str, path: str) -> tuple[str, set[str] | None]:
    """``("present", lines)`` | ``("absent", None)`` | ``("unreadable", None)``.

    ``git show`` returns the same failure for "this path is not in that tree" and
    for "git could not answer" (a partial clone that cannot fetch the blob, a
    resource limit, a damaged object store). The filters SUPPRESS findings on
    absence, so collapsing the two would turn an unanswerable question into a
    green pass — precisely the silence this check exists to remove. ``ls-tree``
    separates them: rc 0 with empty output is a real absence, a non-zero rc is a
    failure.
    """
    rc, out, _ = _run_git(project_root, "ls-tree", "--name-only", ref, "--", path)
    if rc != 0:
        return "unreadable", None
    if not out.strip():
        return "absent", None
    lines = file_lines(project_root, ref, path)
    return ("present", lines) if lines is not None else ("unreadable", None)


def read_side(
    project_root: Path, ref: str, path: str, problems: list[str] | None = None,
) -> tuple[set[str] | None, bool]:
    """``(lines, readable)`` for one side of a comparison; ``None`` lines = absent.

    The detector reads four sides — the merged-in parent, the merge base, the
    branch's own pre-merge side, and ``head`` — and each of them treats "I could
    not read this" as a meaningful answer if left alone: an unreadable merged-in
    parent reads as "they deleted it too" and drops the path from the comparison
    entirely. That is a suppression nobody is told about, which is the one thing
    this check may never do (external code review). Every side now goes through
    here, so a read failure is recorded and disclosed rather than inferred.
    """
    state, lines = tip_state(project_root, ref, path)
    if state == "unreadable":
        if problems is not None:
            problems.append(f"cannot read {path} at {ref[:12]}")
        return None, False
    return lines, True


def resolve_default_ref(project_root: Path, default_branch: str) -> str:
    """The ref the branch actually integrates, not merely the one it was asked about.

    Iterate branches are brought current from ``origin/<default>``
    (``ensure_current`` merges that ref), while the F11 call site passes the bare
    local branch name. When the local ref lags, ``merge-base --is-ancestor`` fails
    for every merge that brought newer content and those merges are skipped
    outright — measured on a real branch: 6 integration merges seen against the
    current tip, 2 against a tip one commit older, 1 against a tip three older.
    A check that quietly shrinks is the same disease as a check that never fires.

    Four outcomes, all explicit, because "it failed" and "it answered no" must not
    be conflated (external plan review):

    * ``origin/<name>`` does not resolve — no remote, which is every test repo
      here — keep the local ref;
    * the local ref is an ancestor of it — the remote is strictly newer, use it;
    * it is not — diverged, or the local ref is ahead — keep the local ref;
    * git failed — keep the local ref, changing nothing on a repository whose
      state we could not read.

    Idempotent: given ``origin/main`` the probe for ``origin/origin/main`` fails
    and the argument comes back unchanged.
    """
    remote = f"origin/{default_branch}"
    rc, _, _ = _run_git(project_root, "rev-parse", "--verify", f"{remote}^{{commit}}")
    if rc != 0:
        return default_branch
    rc, _, _ = _run_git(project_root, "merge-base", "--is-ancestor", default_branch, remote)
    return remote if rc == 0 else default_branch


def is_subsequence(needle: list[str], hay: list[str]) -> bool:
    """Greedy token-subsequence test; an empty ``needle`` is never contained."""
    if not needle or len(needle) > len(hay):
        return False
    i = 0
    for token in hay:
        if token == needle[i]:
            i += 1
            if i == len(needle):
                return True
    return False


def tokens_in_order(needle: str, hay: str) -> bool:
    """Does every whitespace-separated token of ``needle`` appear, in order, in ``hay``?

    Order-preserving containment, not a similarity score — there is no threshold
    to tune and no partial credit. Tokens match whole, so ``foo`` is not found in
    ``foobar``. An empty ``needle`` returns ``False`` rather than the vacuous
    ``True``: it cannot occur (blank lines never reach here) but "nothing
    survived" must never read as "everything survived".

    This proves the words survive, **not** the meaning — a negation inserted into
    the other side's line passes, and is accepted. See
    :mod:`silent_revert_filters` for why that trade is made and what bounds it.
    """
    return is_subsequence(needle.split(), hay.split())


def replacement_hunks(
    project_root: Path, ref: str, head: str, path: str,
) -> list[tuple[set[str], list[str]]]:
    """``[(deleted, added)]`` per minimal diff hunk of ``ref..head`` for one path.

    ``-U0`` is what makes the pairing meaningful: with no context lines a hunk is
    exactly one contiguous changed region, so a line added in the same hunk as a
    deletion is the line that replaced it. With the default three lines of
    context, two unrelated edits a few lines apart would share a hunk and vouch
    for each other.

    Parsing starts only after the first ``@@``, so a deleted ``---`` line (a
    markdown rule, say) is never mistaken for the diff's own file header. A diff
    with no hunks at all — a binary file, an unreadable path — yields ``[]``,
    which suppresses nothing.

    ``-w`` keeps the hunks and the findings agreeing about what "the same line"
    means. Lines are compared everywhere else after ``.strip()``, so a pure
    re-indent produces no finding — but git, diffing raw bytes, would see every
    line as changed and collapse the file into ONE hunk, inside which any added
    line could vouch for any deleted one. That is the unbounded matching the
    design rejected, reachable by reformatting (Stage-3 review).
    """
    rc, out, _ = _run_git(project_root, "diff", "-U0", "-w", ref, head, "--", path)
    if rc != 0:
        return []
    hunks: list[tuple[set[str], list[str]]] = []
    deleted: set[str] = set()
    added: list[str] = []
    started = False
    for raw in out.splitlines():
        if raw.startswith("@@"):
            if started and (deleted or added):
                hunks.append((deleted, added))
            deleted, added, started = set(), [], True
        elif not started:
            continue
        elif raw.startswith("-"):
            if significant_line(raw[1:]):
                deleted.add(raw[1:].strip())
        elif raw.startswith("+"):
            if significant_line(raw[1:]):
                added.append(raw[1:].strip())
    if started and (deleted or added):
        hunks.append((deleted, added))
    return hunks


__all__ = [
    "file_lines",
    "is_subsequence",
    "replacement_hunks",
    "resolve_default_ref",
    "significant_line",
    "tip_state",
    "tokens_in_order",
]
