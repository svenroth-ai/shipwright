"""Single source of truth for the runtime/tracked agent-doc artifact split.

Three agent-doc Markdown files are written by every plugin's Stop hook
(handoff, dashboard, triage) AND by iterate-finalize. Prior to
iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox
both producers wrote to ``.shipwright/agent_docs/<name>.md`` — every
session left main dirty with 3 modified files even when no code work
happened (Stop fires per turn × 12 plugins).

Split:

* **runtime/** — gitignored. Stop hooks write here on every turn. Live
  state; consumers reading mid-session inspect this.
* **tracked**  — committed. Only iterate-finalize writes here (single
  producer, ADR-088 pattern extended from the 5 compliance MDs).
  Finalize copies runtime → tracked atomically, then unlinks runtime.

Consumers that want **snapshot semantics** (verifiers, audits, compliance
reports consumed at iterate boundaries) read tracked. Consumers that want
**live state** (operator inspection between iterates) read runtime via
:func:`read_runtime_or_tracked`.
"""

from __future__ import annotations

from pathlib import Path

# Anchored under the canonical agent_docs home — the gitignore re-include
# block allows /.shipwright/agent_docs/ but the runtime/ subdir is
# re-excluded. Single string literal to keep grep-ability.
AGENT_DOCS_DIRNAME = ".shipwright/agent_docs"
RUNTIME_SUBDIR = "runtime"

# The three agent-doc Markdown files that participate in the runtime/tracked
# split. Stop hooks write the runtime variant; iterate-finalize snapshots
# runtime → tracked. Keys are bare names (without .md suffix) for clarity
# in code that wants to reason about the artifact set.
TRACKED_AGENT_DOC_NAMES: tuple[str, ...] = (
    "session_handoff",
    "build_dashboard",
    "triage_inbox",
)


def runtime_dir(project_root: Path) -> Path:
    """Return the runtime/ directory path. Does NOT create."""
    return project_root / AGENT_DOCS_DIRNAME / RUNTIME_SUBDIR


def tracked_path(project_root: Path, name: str) -> Path:
    """Return the tracked Markdown path for ``name`` (without `.md`).

    Always returns a path under ``.shipwright/agent_docs/<name>.md``,
    regardless of whether ``name`` is in ``TRACKED_AGENT_DOC_NAMES``.
    """
    return project_root / AGENT_DOCS_DIRNAME / f"{name}.md"


def runtime_path(project_root: Path, name: str) -> Path:
    """Return the runtime Markdown path for ``name`` (without `.md`)."""
    return runtime_dir(project_root) / f"{name}.md"


def read_runtime_or_tracked(project_root: Path, name: str) -> str | None:
    """Return live runtime content if present, else tracked content, else None.

    Use this from consumers that want **fresh state** — e.g. an operator
    dashboard that wants to show the latest triage aggregation even
    between iterates. Most framework readers (verifiers, audits) should
    read tracked directly via :func:`tracked_path` because they want
    snapshot semantics tied to the last iterate commit.
    """
    rp = runtime_path(project_root, name)
    if rp.is_file():
        try:
            return rp.read_text(encoding="utf-8")
        except OSError:
            pass
    tp = tracked_path(project_root, name)
    if tp.is_file():
        try:
            return tp.read_text(encoding="utf-8")
        except OSError:
            pass
    return None


def ensure_path_within_project_root(candidate: Path, project_root: Path) -> Path:
    """Resolve ``candidate`` and assert it is under ``project_root``.

    Raises ``ValueError`` on path-escape attempts (absolute paths outside
    the project, symlinks that point above the root, ``..`` traversal
    that lands outside, OR symlinks anywhere in the chain — see below).
    Returns the resolved path for the caller to use as a writable target.

    Symlink refusal (code-reviewer MEDIUM #2, 2026-05-27): a symlink at
    ``candidate`` itself OR at ``candidate.parent`` is refused even when
    the resolved target lies under ``project_root``. Otherwise a TOCTOU
    race between this resolve() call and the eventual mkdir/write would
    let an attacker swap a symlink under us and redirect the write.
    Walks the parent chain up to ``project_root`` looking for symlinks.

    Used by :data:`aggregate_triage.parser` when ``--out-dir`` is supplied
    so the CLI cannot be coerced into writing outside the project tree.
    """
    proj = project_root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(proj)
    except ValueError as exc:
        raise ValueError(
            f"path {candidate} resolved to {resolved}, which escapes "
            f"project root {proj}"
        ) from exc

    # Walk from the candidate up to project_root, refusing symlinks at
    # any rung. ``candidate`` may not exist yet (out-dir to be created);
    # check `is_symlink()` only on path components that DO exist.
    current = candidate
    while True:
        try:
            current_resolved = current.resolve()
        except (OSError, RuntimeError):
            break
        if current.exists() and current.is_symlink():
            raise ValueError(
                f"path component {current} is a symlink; refusing for "
                "write-safety (TOCTOU race)"
            )
        if current_resolved == proj or current.parent == current:
            break
        current = current.parent
    return resolved
