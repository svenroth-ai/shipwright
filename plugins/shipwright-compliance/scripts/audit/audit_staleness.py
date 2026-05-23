"""Group E — compliance document snapshot-provenance audit.

Replaces the pre-2026-05-23 fresh-render byte-compare. The current audit
verifies that on-disk compliance MDs match the version committed in the
LAST iterate-finalize commit (identified by a ``Run-ID:`` trailer in the
commit body AND a tree modification under ``.shipwright/compliance/``).

Rationale: the previous design treated tracked Markdown as both live
derived state AND committed historical artifact — those semantics
conflict (any non-iterate commit can shift live state without touching
the tracked file, producing a perpetual stream of E1-E5 false positives
in the triage inbox). The new design is purely **snapshot integrity**:

  * On-disk == last iterate snapshot → green.
  * On-disk != last iterate snapshot → ``stale`` (someone hand-edited
    or partially-regenerated a tracked MD outside iterate finalize).
  * No iterate-finalize commit exists yet → ``snapshot_unavailable``
    on the report, ``any_stale=False`` (greenfield-safe).

Iterate finalize remains the sole producer of these tracked MDs; live
state can be inspected on demand via ``update_compliance.py`` (which
writes a fresh, uncommitted regen) but it is no longer required for
the audit to be accurate.

Semantic shift documented in
``iterate-2026-05-23-compliance-md-single-producer``.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


def _load_events_log_resolver():
    """Load ``resolve_main_repo_root`` via the pollution-free shared loader.

    Plain ``from lib.events_log import resolve_main_repo_root`` pins
    ``lib`` to ``shared/scripts/lib`` for the rest of the test session,
    which shadows the compliance plugin's own ``lib`` package and breaks
    ``test_enforcement_hooks`` collection (it does ``from lib.thresholds
    import ...``). ``audit_adapters.load_shared_lib`` registers the module
    under a sentinel name and never touches the ``lib`` slot.
    """
    try:
        from scripts.audit.audit_adapters import load_shared_lib
        events_log = load_shared_lib("events_log")
        return events_log.resolve_main_repo_root
    except Exception:  # noqa: BLE001 — defensive fall-back
        def _noop(_project_root: Path):
            return None
        return _noop


_resolve_main_repo_root = _load_events_log_resolver()


# Strip every ``Generated: ...`` line so the snapshot byte-compare ignores
# the volatile timestamp banner. Same regex as the legacy fresh-render
# audit — both sides of the comparison still need normalisation.
HEADER_STRIP_RE = re.compile(r"(?m)^Generated:.*\n?")

_GIT_TIMEOUT_SECONDS = 10


def normalize(text: str) -> str:
    """Strip timestamp/header noise so byte-compare ignores mtime-driven churn."""
    return HEADER_STRIP_RE.sub("", text)


@dataclass
class DocInfo:
    """Registry entry describing a tracked compliance doc."""

    key: str  # "rtm" | "test_evidence" | "change_history" | "sbom" | "dashboard"
    rel_path: str  # ".shipwright/compliance/traceability-matrix.md" etc.


COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"

# Single source of truth for the doc set Group E audits.
DOC_REGISTRY: tuple[DocInfo, ...] = (
    DocInfo("rtm", f"{COMPLIANCE_DIR}/traceability-matrix.md"),
    DocInfo("test_evidence", f"{COMPLIANCE_DIR}/test-evidence.md"),
    DocInfo("change_history", f"{COMPLIANCE_DIR}/change-history.md"),
    DocInfo("sbom", f"{COMPLIANCE_DIR}/sbom.md"),
    DocInfo("dashboard", f"{COMPLIANCE_DIR}/dashboard.md"),
)


@dataclass
class DocStalenessResult:
    """Per-document snapshot comparison outcome."""

    doc: str
    rel_path: str
    exists: bool
    stale: bool
    first_diff_line: int | None = None  # 1-based, post-normalization
    line_delta: int = 0  # len(on_disk_lines) - len(snapshot_lines) post-norm
    error: str | None = None  # set on git error or snapshot-side absence
    snapshot_sha: str | None = None  # the snapshot the comparison was against

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StalenessReport:
    """Aggregate Group E result."""

    docs: list[DocStalenessResult] = field(default_factory=list)
    snapshot_sha: str | None = None
    snapshot_unavailable: bool = False

    @property
    def stale_docs(self) -> list[DocStalenessResult]:
        return [d for d in self.docs if d.stale]

    @property
    def any_stale(self) -> bool:
        return bool(self.stale_docs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "any_stale": self.any_stale,
            "stale_count": len(self.stale_docs),
            "total": len(self.docs),
            "snapshot_sha": self.snapshot_sha,
            "snapshot_unavailable": self.snapshot_unavailable,
            "docs": [d.to_dict() for d in self.docs],
        }


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def _resolve_git_root(project_root: Path) -> Path:
    """Return the canonical main-repo root (worktree-aware), or project_root."""
    main = _resolve_main_repo_root(project_root)
    return main or project_root


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
    )


def find_snapshot_commit(project_root: Path) -> str | None:
    """Find the most recent commit qualifying as a compliance snapshot.

    Qualifying = ``Run-ID:`` trailer in the commit body AND tree
    modifications include at least one path under ``.shipwright/compliance/``.
    ``--diff-filter=AM`` includes both Added (very first iterate-finalize
    that introduces the dir) and Modified (subsequent iterates).

    Worktree-aware: invoked from inside a linked worktree, it resolves
    the main repo's git history so the audit sees the same baseline.

    Returns the commit SHA, or ``None`` when no qualifying commit exists
    (greenfield project, pre-adoption history, or git unavailable).
    """
    git_root = _resolve_git_root(project_root)
    try:
        proc = _git(
            [
                "log",
                "--grep=Run-ID:",
                "--diff-filter=AM",
                "--format=%H",
                "-1",
                "--",
                COMPLIANCE_DIR,
            ],
            cwd=git_root,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None


def _read_snapshot_text(
    project_root: Path,
    snapshot_sha: str,
    rel_path: str,
) -> tuple[str | None, str | None]:
    """Return ``(content, error)`` from ``git show <sha>:<rel_path>``.

    ``content`` is the file's text at the snapshot. ``error`` is set when
    the file didn't exist at the snapshot (or git failed); ``content`` is
    then ``None``.
    """
    git_root = _resolve_git_root(project_root)
    try:
        proc = _git(["show", f"{snapshot_sha}:{rel_path}"], cwd=git_root)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return None, f"git unavailable: {exc!r}"
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        return None, f"snapshot side missing: {stderr or 'git show non-zero exit'}"
    return proc.stdout, None


def _first_diff_line(a: str, b: str) -> int | None:
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    for idx, (la, lb) in enumerate(zip(a_lines, b_lines), start=1):
        if la != lb:
            return idx
    if len(a_lines) != len(b_lines):
        return min(len(a_lines), len(b_lines)) + 1
    return None


def _line_count(text: str) -> int:
    return len(text.splitlines())


def compare_doc(
    project_root: Path,
    doc: DocInfo,
    snapshot_sha: str,
) -> DocStalenessResult:
    """Compare on-disk ``doc`` to the version committed at ``snapshot_sha``.

    Both sides are normalised (``Generated:`` lines stripped) before
    comparison so the volatile banner doesn't drive false drift.
    """
    on_disk_path = project_root / doc.rel_path

    if not on_disk_path.exists():
        return DocStalenessResult(
            doc=doc.key,
            rel_path=doc.rel_path,
            exists=False,
            stale=True,
            error="on-disk file missing",
            snapshot_sha=snapshot_sha,
        )

    try:
        on_disk = on_disk_path.read_text(encoding="utf-8")
    except OSError as exc:
        return DocStalenessResult(
            doc=doc.key,
            rel_path=doc.rel_path,
            exists=True,
            stale=True,
            error=f"read_error: {exc}",
            snapshot_sha=snapshot_sha,
        )

    snapshot_text, snapshot_err = _read_snapshot_text(
        project_root, snapshot_sha, doc.rel_path,
    )
    if snapshot_text is None:
        return DocStalenessResult(
            doc=doc.key,
            rel_path=doc.rel_path,
            exists=True,
            stale=True,
            error=snapshot_err,
            snapshot_sha=snapshot_sha,
        )

    disk_norm = normalize(on_disk)
    snap_norm = normalize(snapshot_text)
    if disk_norm == snap_norm:
        return DocStalenessResult(
            doc=doc.key,
            rel_path=doc.rel_path,
            exists=True,
            stale=False,
            snapshot_sha=snapshot_sha,
        )

    return DocStalenessResult(
        doc=doc.key,
        rel_path=doc.rel_path,
        exists=True,
        stale=True,
        first_diff_line=_first_diff_line(disk_norm, snap_norm),
        line_delta=_line_count(disk_norm) - _line_count(snap_norm),
        snapshot_sha=snapshot_sha,
    )


def check_staleness(
    project_root: Path,
    *,
    doc_filter: Iterable[str] | None = None,
) -> StalenessReport:
    """Run Group E against ``project_root``.

    No ``data`` / renderer dependency — the audit reads the last
    iterate-finalize snapshot from git history and byte-compares against
    on-disk files. Greenfield projects (no qualifying commit) yield an
    empty report with ``snapshot_unavailable=True`` and ``any_stale=False``.
    """
    wanted = set(doc_filter) if doc_filter is not None else None

    snapshot_sha = find_snapshot_commit(project_root)
    if snapshot_sha is None:
        return StalenessReport(
            docs=[],
            snapshot_sha=None,
            snapshot_unavailable=True,
        )

    report = StalenessReport(snapshot_sha=snapshot_sha)
    for doc in DOC_REGISTRY:
        if wanted is not None and doc.key not in wanted:
            continue
        report.docs.append(compare_doc(project_root, doc, snapshot_sha))
    return report
