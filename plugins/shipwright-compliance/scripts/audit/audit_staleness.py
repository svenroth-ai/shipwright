"""Group E — compliance document content-staleness detection.

Regenerates each tracked compliance doc in memory from the current
``ComplianceData``, strips the volatile ``Generated:`` header line (regex,
not fixed line numbers — per plan v5 review finding), and byte-compares
against the on-disk file. This catches *content rot* that mtime-based
checks (Phase-Quality I1-I4) cannot see: a doc whose mtime is fresh but
whose bytes are wrong because the last regeneration missed an FR added
manually.

Plan v7 Option Z, Group E (§ "Compliance Document Staleness").
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

# Strip every ``Generated: ...`` line anywhere in the doc (multiline mode).
# Consumes the trailing newline too so the surrounding diff stays clean.
# If generators add more volatile headers later, extend this regex.
HEADER_STRIP_RE = re.compile(r"(?m)^Generated:.*\n?")


def normalize(text: str) -> str:
    """Strip timestamp/header noise so byte-compare ignores mtime-driven churn."""
    return HEADER_STRIP_RE.sub("", text)


@dataclass
class DocInfo:
    """Registry entry describing a tracked compliance doc."""

    key: str  # "rtm" | "test_evidence" | "change_history" | "sbom" | "dashboard"
    rel_path: str  # e.g. "compliance/traceability-matrix.md"


# Single source of truth for the doc set that Group E scans + (Step 7) fixes.
DOC_REGISTRY: tuple[DocInfo, ...] = (
    DocInfo("rtm", "compliance/traceability-matrix.md"),
    DocInfo("test_evidence", "compliance/test-evidence.md"),
    DocInfo("change_history", "compliance/change-history.md"),
    DocInfo("sbom", "compliance/sbom.md"),
    DocInfo("dashboard", "compliance/dashboard.md"),
)


@dataclass
class DocStalenessResult:
    """Per-document staleness comparison outcome."""

    doc: str
    rel_path: str
    exists: bool
    stale: bool
    first_diff_line: int | None = None  # 1-based, post-normalization
    line_delta: int = 0  # len(fresh_lines) - len(on_disk_lines), post-normalization
    error: str | None = None  # set when the generator threw

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StalenessReport:
    """Aggregate result for a full Group E pass."""

    docs: list[DocStalenessResult] = field(default_factory=list)

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
            "docs": [d.to_dict() for d in self.docs],
        }


def _first_diff_line(a: str, b: str) -> int | None:
    """Return the 1-based line number of the first differing line.

    ``None`` when the strings match after normalization (caller should not
    reach here when stale=False, but we guard anyway).
    """
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    for idx, (la, lb) in enumerate(zip(a_lines, b_lines), start=1):
        if la != lb:
            return idx
    # All overlapping lines match but lengths differ — first diff is the
    # first line past the shorter prefix.
    if len(a_lines) != len(b_lines):
        return min(len(a_lines), len(b_lines)) + 1
    return None


def _line_count(text: str) -> int:
    return len(text.splitlines())


def compare_doc(
    project_root: Path,
    doc: DocInfo,
    fresh_content: str,
) -> DocStalenessResult:
    """Compare ``fresh_content`` against the on-disk copy of ``doc``.

    Both sides are normalized (``Generated:`` lines stripped) before
    comparison so mtime/timestamp differences don't trigger a false stale.
    """
    path = project_root / doc.rel_path
    fresh_norm = normalize(fresh_content)

    if not path.exists():
        # Missing on-disk means stale by definition (the doc should exist).
        return DocStalenessResult(
            doc=doc.key, rel_path=doc.rel_path, exists=False,
            stale=True, first_diff_line=None,
            line_delta=_line_count(fresh_norm),
        )

    try:
        on_disk = path.read_text(encoding="utf-8")
    except OSError as exc:
        return DocStalenessResult(
            doc=doc.key, rel_path=doc.rel_path, exists=True,
            stale=True, error=f"read_error: {exc}",
        )

    disk_norm = normalize(on_disk)
    if fresh_norm == disk_norm:
        return DocStalenessResult(
            doc=doc.key, rel_path=doc.rel_path, exists=True,
            stale=False,
        )

    return DocStalenessResult(
        doc=doc.key, rel_path=doc.rel_path, exists=True, stale=True,
        first_diff_line=_first_diff_line(fresh_norm, disk_norm),
        line_delta=_line_count(fresh_norm) - _line_count(disk_norm),
    )


# A ``Renderer`` takes ComplianceData and returns the doc content as a str.
Renderer = Callable[[Any], str]


def default_renderers() -> dict[str, Renderer]:
    """Return the stock renderer mapping (DocInfo.key → str-producing fn).

    Imports are localized so ``audit_staleness.py`` stays importable from
    tests even when the compliance plugin's own deps aren't installed.
    """
    from scripts.lib.change_history import generate as render_change_history
    from scripts.lib.compliance_report import generate as render_dashboard
    from scripts.lib.rtm_generator import generate as render_rtm
    from scripts.lib.sbom_generator import generate as render_sbom
    from scripts.lib.test_evidence import generate as render_test_evidence

    return {
        "rtm": render_rtm,
        "test_evidence": render_test_evidence,
        "change_history": render_change_history,
        "sbom": render_sbom,
        "dashboard": render_dashboard,
    }


def check_staleness(
    project_root: Path,
    data: Any,
    *,
    renderers: dict[str, Renderer] | None = None,
    doc_filter: Iterable[str] | None = None,
) -> StalenessReport:
    """Run Group E against ``project_root`` using ``data``.

    Args:
        project_root: Project root.
        data: ``ComplianceData`` instance (opaque here — passed verbatim to
            each renderer).
        renderers: Optional renderer override for tests. Defaults to the
            production generators.
        doc_filter: If provided, restrict the scan to the named docs.
    """
    renderers = renderers or default_renderers()
    wanted = set(doc_filter) if doc_filter is not None else None
    report = StalenessReport()

    for doc in DOC_REGISTRY:
        if wanted is not None and doc.key not in wanted:
            continue
        render = renderers.get(doc.key)
        if render is None:
            report.docs.append(DocStalenessResult(
                doc=doc.key, rel_path=doc.rel_path, exists=False,
                stale=True, error="no_renderer_registered",
            ))
            continue
        try:
            fresh = render(data)
        except Exception as exc:  # noqa: BLE001 — convert to structured finding
            report.docs.append(DocStalenessResult(
                doc=doc.key, rel_path=doc.rel_path, exists=False,
                stale=True, error=f"render_error: {type(exc).__name__}: {exc}",
            ))
            continue
        report.docs.append(compare_doc(project_root, doc, fresh))

    return report
