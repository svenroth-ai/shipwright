"""SSoT drift-protection for decision-drop directory resolution.

Iterate F3 writes one ADR JSON drop per run under
``.shipwright/agent_docs/decision-drops/`` (``write_decision_drop.py``) and
``/shipwright-changelog`` later folds them into ``decision_log.md``
(``aggregate_decisions.py``). The drop dir is **repo-scoped**: an iterate run
executes inside an ephemeral worktree whose copy ``git worktree remove``
discards. Any code that may run from inside a worktree MUST resolve the drop
dir against the MAIN repo via ``lib.repo_root.resolve_main_repo_root`` — a
raw ``project_root / ... / "decision-drops"`` join from inside a worktree
reads/writes a throwaway copy.

This meta-test mirrors ``test_events_log_ssot.py`` — the same registry-driven
SSoT pattern (shipwright-iterate SKILL.md "Registry-driven SSoT meta-test
rule"), in both directions:

- Forward: every worktree-reachable decision-drop site uses the resolver.
- Coverage: every raw decision-drop join in ``shared/scripts`` is either
  worktree-aware or an allowlisted main-repo-only site (reason documented).
- Reverse: every allowlist entry still exists and still has a raw join.

Origin: every iterate ADR since unconditional worktree isolation was silently
lost because ``write_decision_drop.py`` used a raw join — the verifier
``iterate_checks.py`` shared the same latent bug
(iterate-2026-05-19-fix-decision-drop-worktree).
"""

from __future__ import annotations

import re
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# Files that build a decision-drop path AND may run from inside an iterate
# worktree — MUST resolve the dir worktree-aware via resolve_main_repo_root.
_WORKTREE_REACHABLE = {
    "tools/write_decision_drop.py",        # iterate F3 — the drop producer
    "tools/verifiers/iterate_checks.py",   # iterate F11 finalization verifier
}

# Files that build a decision-drop path but run ONLY in main-repo phases,
# where project_root is always the main repo so the raw join is correct.
# If one of these is ever invoked from a worktree, move it to the resolver.
_MAIN_REPO_ONLY = {
    "tools/verifiers/common.py":
        "C1/C4 phase-quality checks for build/adopt phase verifiers + the "
        "Phase-Quality Stop hook — all run with project_root = main repo",
}

# NB: aggregate_decisions.py is the drop CONSUMER. /shipwright-changelog runs
# it on the main repo, so it is not strictly worktree-reachable — but it
# resolves the dir worktree-aware anyway to stay in lock step with the
# producer (no producer/consumer drift). It therefore satisfies the coverage
# check below as a worktree-aware file, and needs no allowlist entry.

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
    """All production .py under shared/scripts (test files excluded)."""
    for p in sorted(_SHARED_SCRIPTS.rglob("*.py")):
        rel = p.relative_to(_SHARED_SCRIPTS).as_posix()
        if "/tests/" in f"/{rel}" or p.name.startswith("test_"):
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


def test_worktree_reachable_drop_files_use_the_resolver():
    """Forward: every worktree-reachable decision-drop site resolves the dir
    via resolve_main_repo_root — never a raw worktree-local join."""
    for rel in sorted(_WORKTREE_REACHABLE):
        path = _SHARED_SCRIPTS / rel
        assert path.exists(), f"_WORKTREE_REACHABLE entry {rel} no longer exists"
        src = path.read_text(encoding="utf-8")
        assert "resolve_main_repo_root" in src, (
            f"{rel} builds a decision-drop path and is reached from inside an "
            "iterate worktree, but does not resolve it via "
            "repo_root.resolve_main_repo_root — it would read/write a "
            "throwaway worktree copy that `git worktree remove` discards."
        )


def test_no_unaccounted_raw_decision_drop_joins():
    """Coverage: every raw decision-drop join in shared/scripts is either
    worktree-aware (resolve_main_repo_root) or allowlisted main-repo-only."""
    violations = []
    for path, rel in _prod_py_files():
        if not _has_raw_join(path):
            continue
        if "resolve_main_repo_root" in path.read_text(encoding="utf-8"):
            continue  # worktree-aware — raw join is resolved against main repo
        if rel in _MAIN_REPO_ONLY:
            continue  # allowlisted; reason documented in _MAIN_REPO_ONLY
        violations.append(rel)
    assert not violations, (
        "Raw `project_root / ... / decision-drops` join(s) in files that are "
        f"neither worktree-aware nor allowlisted main-repo-only: {violations}. "
        "Resolve the dir via repo_root.resolve_main_repo_root, or — if the "
        "file only ever runs in a main-repo phase — add it to _MAIN_REPO_ONLY "
        "with a reason."
    )


def test_main_repo_only_allowlist_not_stale():
    """Reverse: every _MAIN_REPO_ONLY entry still exists and still has a raw
    decision-drop join — a file migrated to the resolver must be dropped."""
    for rel in sorted(_MAIN_REPO_ONLY):
        path = _SHARED_SCRIPTS / rel
        assert path.exists(), (
            f"_MAIN_REPO_ONLY entry {rel} no longer exists — drop it."
        )
        assert _has_raw_join(path), (
            f"_MAIN_REPO_ONLY entry {rel} no longer builds a raw "
            "decision-drop path — it was migrated; drop it from the allowlist."
        )
