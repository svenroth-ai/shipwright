"""SSoT drift-protection for decision-drop directory resolution.

Iterate F3 writes one ADR JSON drop per run under
``.shipwright/agent_docs/decision-drops/`` (``write_decision_drop.py``) and
``/shipwright-changelog`` later folds them into ``decision_log.md``
(``aggregate_decisions.py``). Since iterate-2026-08-08-track-decision-drops
the directory is **tracked** (only its local ``INDEX.md`` render stays
gitignored), and every drop-dir builder resolves it directly against
``project_root`` — the calling checkout's own tree, whether that's an
iterate worktree (F3, F11) or the main repo (``/shipwright-changelog``).

This inverts the invariant this meta-test used to guard. Before this run,
the directory was gitignored and a worktree-local write would be destroyed
by ``git worktree remove``, so every worktree-reachable site was REQUIRED to
redirect via ``lib.repo_root.resolve_main_repo_root``. Now the directory is
committed as part of the writing iterate's own PR, so that redirect would be
actively wrong: it would land an untracked file directly on the main
checkout with nothing to ever commit it — the same class of silent loss
ADR-049 already caused once (iterate-2026-05-19-fix-decision-drop-worktree),
from the opposite direction.

Same registry-driven SSoT pattern as before (shipwright-iterate SKILL.md
"Registry-driven SSoT meta-test rule"), in both directions:

- Forward: every known decision-drop site does NOT redirect via
  ``resolve_main_repo_root``.
- Coverage: no raw decision-drop join anywhere in the REPO (not just
  ``shared/scripts``) is paired with a ``resolve_main_repo_root`` import in
  the same file.
- Reverse: every registry entry still exists and still builds a raw
  decision-drop join.

The coverage scan is repo-wide, not ``shared/scripts``-only, because a
plugin-side consumer (``plugins/shipwright-compliance/scripts/audit/
group_f.py``) was found still redirecting via ``resolve_main_repo_root``
during this same run, invisible to a ``shared/scripts``-scoped scan — the
narrower scope would have let exactly this class of regression back in.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories never worth scanning: VCS/dep/venv noise and generated worktrees.
_SCAN_EXCLUDE_DIRNAMES = {
    ".git", ".venv", "node_modules", ".worktrees", "__pycache__", ".pytest_cache",
}

# Every known production site that builds a decision-drop path — named so a
# regression reintroducing resolve_main_repo_root at any of THESE specific
# sites fails with the file named, not just "somewhere in the repo" (the
# blanket, unnamed backstop is test_no_unaccounted_decision_drop_site_
# redirects_to_main_root below, which scans every production .py regardless
# of registry membership — this list is a documented subset for named
# coverage, not the sole enforcement; doubt-reviewer MEDIUM #5 flagged an
# earlier version of this comment for reading as if it were exhaustive).
# Test files are deliberately out of the coverage scan's scope too (see
# _prod_py_files) — a stale test asserting behavior this iterate removed
# fails loudly when run, which is a correctness check on ITS OWN, not a gap
# this registry needs to also cover. Paths are repo-root-relative.
_WORKTREE_LOCAL = {
    "shared/scripts/tools/write_decision_drop.py",        # iterate F3 — the drop producer
    "shared/scripts/tools/verifiers/iterate_checks.py",   # iterate F11 finalization verifier
    "shared/scripts/tools/verifiers/decision_log_gate.py",  # F11 ADR-recorded-and-present check
    "shared/scripts/tools/verifiers/common.py",           # C1/C4 iterate-phase-recorded fallbacks
    "shared/scripts/tools/aggregate_decisions.py",        # /shipwright-changelog release fold
    "shared/scripts/lib/decision_drops_index.py",         # local INDEX.md render/rebuild
    "plugins/shipwright-compliance/scripts/audit/group_f.py",  # F5 arch-drift detective
    "shared/tests/test_architecture_md_reflects_arch_impact.py",  # arch-impact drift oracle
}

# A decision-drop path-join. Two shapes, because ``DROP_DIRNAME`` is an
# ambiguous constant name — ``write_changelog_drop.py`` also defines a
# ``DROP_DIRNAME`` (a DIFFERENT value, ``"CHANGELOG-unreleased.d"``):
#   - the literal ``"decision-drops"`` path component — always a drop join;
#   - ``/ DROP_DIRNAME``, but ONLY counted in a file that itself binds
#     ``DROP_DIRNAME = "decision-drops"``.
_LITERAL_JOIN_RE = re.compile(r"""/\s*\(?["']decision-drops["']""")
_CONST_JOIN_RE = re.compile(r"/\s*\(?DROP_DIRNAME\b")
_DECISION_DROP_CONST_RE = re.compile(
    r"""DROP_DIRNAME\s*=\s*["']decision-drops["']"""
)


def _prod_py_files():
    """All production .py in the repo (test files and scan-excluded dirs skipped).

    Repo-wide, not ``shared/scripts``-only — see module docstring for why a
    narrower scope already let one plugin-side site slip past. Walks via
    ``os.walk`` with in-place ``dirnames`` pruning rather than
    ``Path.rglob("*.py")`` — ``rglob`` descends into ``.venv``/``.git``/
    ``.worktrees`` fully before the exclusion filter ever runs, which is slow
    enough to matter on a repo carrying other checkouts under ``.worktrees/``.
    """
    for dirpath, dirnames, filenames in os.walk(_REPO_ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in _SCAN_EXCLUDE_DIRNAMES)
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            p = Path(dirpath) / name
            rel = p.relative_to(_REPO_ROOT).as_posix()
            if "/tests/" in f"/{rel}" or name.startswith("test_"):
                continue
            yield p, rel


def _has_raw_join(path: Path) -> bool:
    """True if the file builds a raw decision-drop path (ignoring # comments).

    ``/ DROP_DIRNAME`` only counts when the file binds
    ``DROP_DIRNAME = "decision-drops"`` — a same-named constant for an
    unrelated drop dir (``write_changelog_drop.py``) must not match.
    """
    src = path.read_text(encoding="utf-8")
    const_is_decision_drop = bool(_DECISION_DROP_CONST_RE.search(src))
    for line in src.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if _LITERAL_JOIN_RE.search(line):
            return True
        if const_is_decision_drop and _CONST_JOIN_RE.search(line):
            return True
    return False


def test_decision_drop_sites_do_not_redirect_to_main_root():
    """Forward: every known decision-drop site must NOT import/call
    resolve_main_repo_root — the directory is tracked and per-checkout now."""
    for rel in sorted(_WORKTREE_LOCAL):
        path = _REPO_ROOT / rel
        assert path.exists(), f"_WORKTREE_LOCAL entry {rel} no longer exists"
        src = path.read_text(encoding="utf-8")
        assert "resolve_main_repo_root" not in src, (
            f"{rel} builds a decision-drop path and resolves it via "
            "resolve_main_repo_root — the directory is TRACKED since "
            "iterate-2026-08-08-track-decision-drops, so a main-root "
            "redirect lands an untracked file on the main checkout with "
            "nothing to ever commit it. Resolve against project_root "
            "directly instead."
        )


def test_no_unaccounted_decision_drop_site_redirects_to_main_root():
    """Coverage: no raw decision-drop join anywhere in shared/scripts is
    paired with a resolve_main_repo_root import in the same file."""
    violations = []
    for path, rel in _prod_py_files():
        if not _has_raw_join(path):
            continue
        if "resolve_main_repo_root" in path.read_text(encoding="utf-8"):
            violations.append(rel)
    assert not violations, (
        "File(s) building a decision-drop path AND importing "
        f"resolve_main_repo_root: {violations}. The directory is tracked "
        "and per-checkout now — resolve it against project_root directly, "
        "and add the file to _WORKTREE_LOCAL above."
    )


def test_registry_not_stale():
    """Reverse: every _WORKTREE_LOCAL entry still exists and still builds a
    raw decision-drop join — a file that stopped building one must be
    dropped from the registry."""
    for rel in sorted(_WORKTREE_LOCAL):
        path = _REPO_ROOT / rel
        assert path.exists(), f"_WORKTREE_LOCAL entry {rel} no longer exists — drop it."
        assert _has_raw_join(path), (
            f"_WORKTREE_LOCAL entry {rel} no longer builds a decision-drop "
            "path — it was migrated or removed; drop it from the registry."
        )
