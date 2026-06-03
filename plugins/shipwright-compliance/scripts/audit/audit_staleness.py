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
AGENT_DOCS_DIR = ".shipwright/agent_docs"
LEGACY_COMPLIANCE_DIRNAME = "compliance"

# Single source of truth for the doc set Group E audits. Extended in
# iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox
# to cover the 3 agent-doc MDs that also follow the single-producer
# pattern (Stop hooks now write to runtime/, finalize is the sole writer
# of the tracked variants).
DOC_REGISTRY: tuple[DocInfo, ...] = (
    DocInfo("rtm", f"{COMPLIANCE_DIR}/traceability-matrix.md"),
    DocInfo("test_evidence", f"{COMPLIANCE_DIR}/test-evidence.md"),
    DocInfo("change_history", f"{COMPLIANCE_DIR}/change-history.md"),
    DocInfo("sbom", f"{COMPLIANCE_DIR}/sbom.md"),
    DocInfo("dashboard", f"{COMPLIANCE_DIR}/dashboard.md"),
    DocInfo("session_handoff", f"{AGENT_DOCS_DIR}/session_handoff.md"),
    DocInfo("build_dashboard", f"{AGENT_DOCS_DIR}/build_dashboard.md"),
    DocInfo("triage_inbox", f"{AGENT_DOCS_DIR}/triage_inbox.md"),
)

# Paths that qualify as a single-producer snapshot when modified in a
# Run-ID-bearing commit. Compliance MDs were the original (PR #78);
# agent-doc MDs joined in iterate-2026-05-27.
SNAPSHOT_PATH_FILTERS: tuple[str, ...] = (
    COMPLIANCE_DIR,
    AGENT_DOCS_DIR,
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

    Qualifying = the commit modified at least one snapshot path AND its
    message marks it as a recognized producer — EITHER a ``Run-ID:``
    trailer (iterate-finalize) OR a ``chore(release)`` subject. The
    changelog/release phase regenerates the tracked MDs and commits them
    as ``chore(release): vX.Y.Z`` WITHOUT a ``Run-ID:`` trailer; before
    this was recognized, every clean release re-flagged those MDs as stale
    because the scan fell back to the older iterate-finalize snapshot
    (C1, 2026-06-02-compliance-detective-realign). A manual
    ``chore(compliance)`` regen is deliberately NOT recognized — that is
    the hand-edit case Group E must still catch.
    ``--diff-filter=AM`` includes both Added (very first finalize that
    introduces the dir) and Modified (subsequent producers).

    Uses ``project_root`` directly — git log is branch-scoped, so an
    iterate worktree's branch lineage (which contains the in-progress
    F6 commit AND the inherited main-branch iterate history) is the
    correct source. Routing through the main repo would miss F6 commits
    on the worktree's branch.

    ``git show`` against the same ``project_root`` resolves blobs from
    the shared ``.git`` common-dir regardless of which branch the main
    repo is on — so worktree-isolation doesn't break the lookup.

    Returns the commit SHA, or ``None`` when no qualifying commit exists
    (greenfield project, pre-adoption history, or git unavailable).
    """
    try:
        proc = _git(
            [
                "log",
                # Match the grep patterns LITERALLY — robust against a global
                # grep.extendedRegexp=true that would otherwise treat the
                # parens in "chore(release)" as a regex group.
                "--fixed-strings",
                # A commit qualifies when its message carries EITHER an
                # iterate-finalize "Run-ID:" trailer OR a changelog/release
                # "chore(release)" subject. Multiple --grep are OR'd (no
                # --all-match). See the docstring for why the release case
                # was added (C1).
                "--grep=Run-ID:",
                "--grep=chore(release)",
                "--diff-filter=AM",
                "--format=%H",
                "-1",
                "--",
                # Widened in iterate-2026-05-27: agent-doc MDs joined the
                # single-producer set, so a Run-ID-bearing commit that
                # touched ONLY agent-doc paths also qualifies.
                *SNAPSHOT_PATH_FILTERS,
            ],
            cwd=project_root,
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
    try:
        proc = _git(["show", f"{snapshot_sha}:{rel_path}"], cwd=project_root)
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
    on_disk_exists = on_disk_path.exists()

    # Peek at the snapshot side BEFORE deciding on missing-side semantics.
    # If a doc was added to DOC_REGISTRY after the snapshot commit (e.g.
    # the agent-doc trio added in iterate-2026-05-27 won't appear in
    # earlier compliance-only snapshots), missing-from-snapshot is benign
    # — neither side has the file yet. Treat as "not present in snapshot,
    # not stale". External review OpenAI #8.
    snapshot_text, snapshot_err = _read_snapshot_text(
        project_root, snapshot_sha, doc.rel_path,
    )
    snapshot_exists = snapshot_text is not None

    if not snapshot_exists:
        # The snapshot commit predates the registry entry for this doc
        # (e.g. the agent-doc trio was added in iterate-2026-05-27; any
        # pre-2026-05-27 snapshot won't have those paths). Whether the
        # on-disk side is present or missing, we are NOT in a position
        # to call this "stale" — there's no canonical version to diff
        # against. Treat as benign "not-in-snapshot".
        #
        # The next finalize commit will introduce these paths, after
        # which subsequent audits compare against a snapshot that DOES
        # have them and any drift becomes real staleness again. External
        # review (code-reviewer, iterate-2026-05-27) HIGH #1.
        return DocStalenessResult(
            doc=doc.key,
            rel_path=doc.rel_path,
            exists=on_disk_exists,
            stale=False,
            error="not-in-snapshot",
            snapshot_sha=snapshot_sha,
        )

    if not on_disk_exists:
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
