"""size_signal — the LOCAL static size proxy for the maintainability dimension.

A cold repo has no ratchet baseline (that needs Shipwright's own history), so
dim 6 is scored instead from the **oversize-file ratio**: the fraction of source
files over the size threshold (the constitution's 300-LOC source ceiling). No
network, no execution — a pure, deterministic scan of the already-capped
:class:`RepoContext` file list.

The engine (``control_grade`` dim 6) turns the ratio into a score; this module
computes the ratio **and** the honest "N/M source files over threshold" detail
string that the projector layers over the engine's ratio-only detail.
"""

from __future__ import annotations

from dataclasses import dataclass

from repo_context import RepoContext

#: The constitution's source-file ceiling — the universal size-discipline line.
SIZE_THRESHOLD_LOC = 300

#: Implementation/source extensions the proxy counts (vendored/build dirs are
#: already pruned by RepoContext). Deliberately excludes data/markup/config.
_SOURCE_EXTS = (
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rb",
    ".java", ".kt", ".rs", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".cs",
    ".php", ".swift", ".scala",
)

#: Bound the per-repo scan (RepoContext already caps the file list at 5000).
_MAX_SOURCE_FILES = 3000
#: A source file larger than this many chars is oversize regardless of exact LOC.
_READ_CAP = 400_000


@dataclass(frozen=True)
class SizeSignal:
    """The static size proxy: ``ratio`` feeds the engine, ``detail`` the report."""

    measurable: bool
    ratio: float | None
    files_over: int
    files_total: int
    detail: str
    truncated: bool


def _line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def compute_size_signal(
    context: RepoContext, *, threshold: int = SIZE_THRESHOLD_LOC
) -> SizeSignal:
    """Fraction of source files over ``threshold`` LOC (deterministic, local)."""
    source = [f for f in context.files if f.endswith(_SOURCE_EXTS)]
    truncated = len(source) > _MAX_SOURCE_FILES
    scan = source[:_MAX_SOURCE_FILES]  # RepoContext.files is already sorted

    files_total = len(scan)
    if files_total == 0:
        return SizeSignal(
            measurable=False, ratio=None, files_over=0, files_total=0,
            detail="no source files to size", truncated=truncated)

    files_over = 0
    for rel in scan:
        text = context.read_text(rel, max_bytes=_READ_CAP)
        if _line_count(text) > threshold or len(text) >= _READ_CAP:
            files_over += 1

    ratio = files_over / files_total
    detail = f"{files_over}/{files_total} source files over {threshold} LOC"
    if truncated:
        detail += f" (first {files_total} of {len(source)} scanned)"
    return SizeSignal(
        measurable=True, ratio=ratio, files_over=files_over,
        files_total=files_total, detail=detail, truncated=truncated)
