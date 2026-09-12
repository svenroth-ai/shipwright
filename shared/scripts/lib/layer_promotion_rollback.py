"""Report validation and rollback helpers for ``lib.layer_promotion_sweep`` —
split out purely to keep that module under the file-size guideline. These
exist to hold ``run_layer_promotion_sweep``'s "never raises, never leaves
residue" contract: every failure mode of the ``promote_required_layers.py``
subprocess call must degrade to a reported result with the worktree back at
its pre-sweep state, never propagate an exception or leave partial writes
behind for a later, unrelated commit to sweep up."""

from __future__ import annotations

from pathlib import Path

from lib.git_base import HOOK_GIT_TIMEOUT, run_git_soft
from lib.layer_promotion_sweep_result import LayerPromotionSweepResult
from lib.planning_discovery import SPEC_FILENAME


def extract_report_fields(report: object) -> tuple[list[str], int, list[str]]:
    """Validate the ``promote_required_layers.py`` report shape and pull out
    the three fields this module reads. ``json.loads`` only rejects a
    syntactically invalid document — a syntactically valid but wrong-shaped
    one (a JSON list, ``null``, or a ``promoted`` entry that isn't an object)
    would otherwise reach an unguarded ``.get()`` and raise past this
    module's own never-raises boundary (external review, PR #725). Raises
    :class:`ValueError` with a short reason for any invalid shape; never
    raises anything else."""
    if not isinstance(report, dict):
        raise ValueError(f"report is not a JSON object (got {type(report).__name__})")
    raw_promoted = report.get("promoted") or []
    if not isinstance(raw_promoted, list) or not all(
        isinstance(d, dict) and isinstance(d.get("fr", ""), str) for d in raw_promoted
    ):
        raise ValueError("'promoted' is not a list of objects with a string 'fr'")
    raw_escalated = report.get("escalated") or []
    if not isinstance(raw_escalated, list):
        raise ValueError("'escalated' is not a list")
    written_paths = report.get("written_spec_paths") or []
    if not isinstance(written_paths, list) or not all(isinstance(p, str) for p in written_paths):
        raise ValueError("'written_spec_paths' is not a list of strings")
    return [d.get("fr", "") for d in raw_promoted], len(raw_escalated), written_paths


def validate_written_paths(worktree_path: Path, written_paths: list[str]) -> list[str]:
    """Reject any ``written_spec_paths`` entry that isn't a ``spec.md`` file
    staying inside ``worktree_path`` — ``extract_report_fields`` only
    checked that these are strings, but they are then handed straight to
    ``git add``/``git diff --cached``/``git commit`` as PATHSPECS and, once
    committed, PUSHED to a public ``chore/layer-promotion-*`` branch and
    opened as a PR. A malformed or compromised ``promote_required_layers.py``
    report naming an absolute path, a ``..`` traversal, or an unrelated
    in-repo file (e.g. ``.env``) would otherwise have that file's content
    staged and published by this delivery flow (external review, PR #725
    round 8) — containment alone (no traversal, no absolute path) does not
    catch the ``.env`` case, since that is already a plain repo-relative
    path; the tool only ever produces genuine ``spec.md`` paths
    (``lib.planning_discovery.SPEC_FILENAME``, from each FR node's own
    ``spec_path`` field), so requiring that exact basename is the precise
    allowlist, not an approximation.

    A value like ``":(glob)**/spec.md"`` passes every check above —
    ``Path(...).name`` is still ``"spec.md"``, and no ``..``/absolute
    component exists — yet, unescaped, IS a Git pathspec: the leading ``:``
    triggers pathspec magic, and even without it Git's default (non-literal)
    pathspec matching treats ``*``/``?``/``[...]`` as wildcards. Handed to
    ``git add``, that stages and publishes every ``spec.md`` the pattern
    matches, not the one literal file this validator approved (external
    review, PR #725 round 12). The final check below — the resolved path
    must be an EXISTING regular file — closes this: a magic/glob string
    resolves to a literal, non-existent path on disk (Git's own pathspec
    interpretation only happens once it reaches Git, never here), so it
    fails this check regardless of what it could later match. The sweep's
    own git calls additionally pass ``--literal-pathspecs`` as defense in
    depth, so even an entry that somehow got past this validator cannot be
    reinterpreted as a pattern by Git itself.

    Returns ``written_paths`` unchanged when every entry is safe; raises
    :class:`ValueError` with a short reason for the first unsafe one."""
    root = worktree_path.resolve()
    for p in written_paths:
        if not p:
            raise ValueError("written_spec_paths contains an empty path")
        candidate = Path(p)
        if candidate.is_absolute():
            raise ValueError(f"written_spec_paths contains an absolute path: {p!r}")
        if ".." in candidate.parts:
            raise ValueError(f"written_spec_paths contains a '..' path segment: {p!r}")
        if candidate.name != SPEC_FILENAME:
            raise ValueError(f"written_spec_paths contains a non-{SPEC_FILENAME} path: {p!r}")
        resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            raise ValueError(f"written_spec_paths path escapes the worktree: {p!r}") from None
        if not resolved.is_file():
            raise ValueError(f"written_spec_paths names a path that is not a real file: {p!r}")
    return written_paths


def untracked_paths(worktree_path: Path) -> set[str] | None:
    """Every untracked path in the worktree, expanded to individual files
    rather than collapsed to a parent directory (``--untracked-files=all``),
    so a later snapshot can be diffed against this one to name exactly which
    files are new. Returns ``None`` if the status call itself fails — a
    caller must then treat cleanup as unsafe rather than assume the
    worktree was empty.

    Uses ``-z`` (NUL-delimited records) rather than plain ``--porcelain``:
    Git C-quotes a path containing a double quote, backslash, control
    character, or (by default, ``core.quotePath``) any non-ASCII byte —
    ``"caf\\303\\251.md"`` on disk becomes the literal 15-character string
    ``"caf\\303\\251.md"`` (quotes and octal escapes included) in plain
    porcelain output. ``line[3:]`` returned that quoted string as if it were
    the real path; handed to ``git clean`` downstream it does not match the
    on-disk file, so a partial write with such a name would survive
    "rollback" while the sweep reports success (external review, PR #725
    round 14). ``-z`` output is unquoted, so ``record[3:]`` is the exact
    filesystem name in every case."""
    result = run_git_soft(
        ["status", "--porcelain", "-z", "--untracked-files=all"], cwd=worktree_path,
    )
    if result.returncode != 0:
        return None
    return {
        record[3:] for record in result.stdout.split("\0")
        if record.startswith("?? ")
    }


def rollback_staged(worktree_path: Path, pre_sha: str, pre_untracked: set[str] | None) -> bool:
    """Undo any write the promotion subprocess left behind — staged or not,
    tracked or a brand-new untracked file — so a failed ``add``/``commit``,
    or a subprocess that partially wrote the ledger/spec before timing out
    or reporting something unusable, never leaves residue for a later,
    unrelated commit to sweep up. ``reset --hard`` alone only reverts
    already-tracked content; a new untracked file the tool created (never
    staged) needs ``git clean`` too — but scoped to exactly the paths that
    are untracked NOW and were not already untracked in ``pre_untracked``,
    never a blanket ``clean -fd``, since that would delete unrelated
    untracked content that predates this sweep entirely (external review,
    PR #725 round 7; round 6 introduced the untracked-file cleanup this
    scopes). When the untracked baseline is unavailable (``None``, before or
    after — a failing ``git status``), this reports FAILURE rather than
    guessing at a clean skip: a partial untracked write from the promotion
    tool may still be sitting in the worktree unremoved, and returning
    ``True`` here would let an ordinary terminal status stand in for a clean
    rollback that never actually happened, silencing the exact escalation
    this return value exists to trigger (external review, PR #725 round 9;
    round 7 treated the unavailable-baseline case as a lesser-risk skip, but
    a caller cannot distinguish that skip from a genuine clean rollback
    without this function saying so). Returns whether the cleanup succeeded
    — a caller must escalate to ``rollback_failed`` when it did not."""
    if not pre_sha:
        return False
    reset = run_git_soft(["reset", "--hard", pre_sha], cwd=worktree_path, timeout=HOOK_GIT_TIMEOUT)
    if reset.returncode != 0:
        return False
    if pre_untracked is None:
        return False
    post_untracked = untracked_paths(worktree_path)
    if post_untracked is None:
        return False
    new_paths = sorted(post_untracked - pre_untracked)
    if not new_paths:
        return True
    # --literal-pathspecs: new_paths are filesystem-derived names (from `git
    # status --porcelain`), not validated the way written_spec_paths is — a
    # newly created file whose NAME itself contains pathspec magic (e.g. a
    # leading ":" or a "*"/"?"/"[...]" wildcard) would otherwise let `git
    # clean` match and remove files beyond the one path it names (external
    # review, PR #725 round 13; mirrors round 12's written_spec_paths fix).
    clean = run_git_soft(
        ["--literal-pathspecs", "clean", "-fd", "--", *new_paths],
        cwd=worktree_path, timeout=HOOK_GIT_TIMEOUT,
    )
    return clean.returncode == 0


def bail(
    worktree_path: Path, pre_sha: str, pre_untracked: set[str] | None,
    status: str, reason: str, promoted: list[str], escalated: int,
) -> LayerPromotionSweepResult:
    """Every non-decisive return path funnels through here once ``pre_sha``
    is known: unconditionally roll the worktree back to it — cheap and safe
    even when nothing was actually written, since ``reset --hard`` onto the
    current HEAD is a no-op and the scoped ``clean`` finds nothing new to
    remove — before reporting the given ``status``. Escalates to the loud
    ``rollback_failed`` when the rollback itself does not succeed, the one
    outcome where residue might still be sitting on this branch."""
    ok = rollback_staged(worktree_path, pre_sha, pre_untracked)
    if not ok:
        return LayerPromotionSweepResult(status="rollback_failed", reason=reason, promoted=promoted, escalated=escalated)
    return LayerPromotionSweepResult(status=status, reason=reason, promoted=promoted, escalated=escalated)


__all__ = ["extract_report_fields", "validate_written_paths", "untracked_paths", "rollback_staged", "bail"]
