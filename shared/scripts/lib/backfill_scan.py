"""Filesystem + spec scan for the shared backfill engine (traceability TT6).

Deterministic, read-only discovery for ``backfill_test_links.py``: enumerate
every test (with the line/indent needed to *insert* a tag), read existing
``@FR`` tags via the frozen shared ``fr_tag_grammar`` reference parser, parse a
spec.md's FR table (active **and** removed rows), and resolve the introducing
commit's ``affected_frs`` (signal ``d``).

Only the SHARED frozen contracts are reused (``fr_tag_grammar`` +
``requirement_model``): the backfill engine lives under ``shared/`` and must not
depend on a plugin. The layer detection + enumeration below mirror the TT1
collector's ``_test_links_io`` (kept in sync by the golden-composition
integration test), because the engine scans *comprehensively* (every test dir)
where the collector scans only conventional roots.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

try:  # flat import off shared/scripts/lib on sys.path (tool + tests).
    from fr_tag_grammar import parse_source
    from fr_tag_grammar import _TEST_DECL_RE  # the ONE shared decl matcher (no divergence)
    from requirement_model import CANONICAL_FR_RE
except ImportError:  # loaded as a package (lib.backfill_scan).
    from .fr_tag_grammar import parse_source, _TEST_DECL_RE  # type: ignore
    from .requirement_model import CANONICAL_FR_RE  # type: ignore

# A canonical FR token anywhere in a path/filename (signal b — exact).
_PATH_FR_RE = re.compile(r"FR-\d{2}\.\d{2}")
# The RTM split-prefix convention: a leading ``NN-`` on the filename ↔ split NN.
_SPLIT_PREFIX_RE = re.compile(r"^(\d{2})-")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")

_PY_SUFFIXES = (".py",)
_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")
_SRC_SUFFIXES = _PY_SUFFIXES + _TS_SUFFIXES
_PRUNE_DIRS = frozenset({
    "node_modules", ".git", ".venv", "venv", "__pycache__", ".worktrees", "dist",
    "build", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".next",
})
_INTEGRATION_DIRS = frozenset({"integration", "integration-tests"})
_TITLE_COLS = ("description", "name", "text", "requirement", "title")


@dataclass(frozen=True)
class FR:
    """One functional requirement as the backfill engine needs it (id/text/status)."""

    id: str
    text: str
    status: str  # "active" | "removed"


@dataclass
class TestRecord:
    """An enumerated test, with what is needed to bind and (idempotently) tag it."""

    test_id: str            # "rel::name"
    rel_path: str
    name: str
    layer: str
    decl_line: int          # 0-based line index of the test declaration / def
    indent: int             # leading-space count for an inserted tag
    existing_frs: list[str] = field(default_factory=list)

    @property
    def is_tagged(self) -> bool:
        return bool(self.existing_frs)


def detect_layer(rel_path: str) -> str:
    """Classify a test file's layer from its path (unit | integration | e2e)."""
    norm = rel_path.replace("\\", "/").lower()
    parts = norm.split("/")
    name = parts[-1]
    if "e2e" in parts or ".e2e." in name:
        return "e2e"
    if _INTEGRATION_DIRS & set(parts) or ".integration.test." in name or ".integration.spec." in name:
        return "integration"
    if name.endswith((".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx")):
        return "e2e"
    return "unit"


def split_of_path(rel_path: str) -> str | None:
    """Return the ``NN`` split prefix of a filename, or ``None`` (signal b)."""
    m = _SPLIT_PREFIX_RE.match(Path(rel_path).name)
    return m.group(1) if m else None


def path_fr_tokens(rel_path: str) -> list[str]:
    """Canonical FR ids embedded in a path (signal b — exact match)."""
    return _PATH_FR_RE.findall(rel_path.replace("\\", "/"))


def iter_test_files(roots: list[Path], base: Path):
    """Yield ``(abs_path, rel_path)`` for every test source file under ``roots``."""
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _SRC_SUFFIXES:
                continue
            if any(part in _PRUNE_DIRS for part in path.parts):
                continue
            name = path.name.lower()
            is_test = (
                name.startswith("test_") or name.endswith("_test.py")
                or ".test." in name or ".spec." in name
            )
            if not is_test or path in seen:
                continue
            seen.add(path)
            yield path, path.relative_to(base).as_posix()


def _enumerate(rel_path: str, source: str) -> list[tuple[str, int, int]]:
    """Return ``(name, decl_line, indent)`` for every test declared in a file."""
    low = rel_path.lower()
    if low.endswith(_PY_SUFFIXES):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        return [
            (n.name, n.lineno - 1, n.col_offset)
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")
        ]
    if low.endswith(_TS_SUFFIXES):
        out = []
        for i, line in enumerate(source.splitlines()):
            m = _TEST_DECL_RE.search(line)
            if m:
                out.append((m.group("title"), i, len(line) - len(line.lstrip())))
        return out
    return []


def scan_tests(roots: list[Path], base: Path) -> list[TestRecord]:
    """Enumerate every test and attach its existing ``@FR`` tags (frozen grammar)."""
    records: list[TestRecord] = []
    for abs_path, rel_path in iter_test_files(roots, base):
        source = abs_path.read_text(encoding="utf-8", errors="ignore")
        layer = detect_layer(rel_path)
        res = parse_source(rel_path, source)
        by_test: dict[str, list[str]] = {}
        for h in res.hits:
            frs = by_test.setdefault(h.test, [])
            if h.fr_id not in frs:
                frs.append(h.fr_id)
        for name, decl_line, indent in _enumerate(rel_path, source):
            test_id = f"{rel_path}::{name}"
            records.append(TestRecord(
                test_id=test_id, rel_path=rel_path, name=name, layer=layer,
                decl_line=decl_line, indent=indent,
                existing_frs=list(by_test.get(test_id, [])),
            ))
    return records


def _row_cells(line: str) -> list[str] | None:
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


def parse_frs(spec_text: str) -> list[FR]:
    """Parse a spec.md FR table into ``FR`` records — active AND removed rows.

    Unlike ``drift_parsers.parse_fr_table`` (which drops removed rows), the
    backfill engine needs the removed set to categorise ``confirmed`` /
    ``possible`` orphans, so this loop keeps both with a ``status``.
    """
    out: list[FR] = []
    in_removed = False
    removed_level = 0
    header: dict[str, int] | None = None
    for line in spec_text.splitlines():
        h = _HEADING_RE.match(line)
        if h:
            level = len(h.group(1))
            if h.group(2).strip().lower().startswith("removed requirements"):
                in_removed, removed_level = True, level
            elif in_removed and level <= removed_level:
                in_removed = False
            continue
        cells = _row_cells(line)
        if not cells or len(cells) < 2:
            continue
        if not CANONICAL_FR_RE.match(cells[0]):
            low = [c.lower() for c in cells]
            if "priority" in low:
                header = {n: i for i, n in enumerate(low)}
            continue
        fr_id = cells[0]
        text = ""
        if header:
            for n in _TITLE_COLS:      # _TITLE_COLS never contains "priority"
                idx = header.get(n)
                if idx is not None and idx < len(cells):
                    text = cells[idx]
                    break
        if not text:
            text = cells[1] if len(cells) > 1 else ""
        out.append(FR(id=fr_id, text=text, status="removed" if in_removed else "active"))
    return out


def _load_events_fr_by_commit(project_root: Path) -> dict[str, set[str]]:
    # Locate the event log via the one SSoT resolver (events_log), never a raw
    # join — pinned by shared/tests/test_events_log_ssot.py.
    try:
        from events_log import resolve_events_path
    except ImportError:  # loaded as a package (lib.backfill_scan)
        from .events_log import resolve_events_path  # type: ignore
    path = resolve_events_path(project_root)
    result: dict[str, set[str]] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        commit = event.get("commit")
        frs = event.get("affected_frs")
        if commit and frs:
            result.setdefault(commit, set()).update(f for f in frs if CANONICAL_FR_RE.match(f))
    return result


def _file_introducing_commits(project_root: Path, wanted: set[str]) -> dict[str, str]:
    """One ``git log`` pass → ``{rel_path: introducing_sha}`` for every wanted file.

    Batched (not one ``git log`` per file — O(N) subprocesses on an adopt/TT7-scale
    repo): a single ``--diff-filter=A --name-only --reverse`` walk visits every
    add oldest-first, so the FIRST add of a file is its introducing commit.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "log", "--diff-filter=A",
             "--name-only", "--format=%x00%H", "--reverse"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if out.returncode != 0:
        return {}
    intro: dict[str, str] = {}
    sha: str | None = None
    for line in out.stdout.splitlines():
        if line.startswith("\x00"):          # a \x00<sha> commit-header line
            sha = line[1:].strip()
        elif line.strip() and sha:
            f = line.strip().replace("\\", "/")
            if f in wanted and f not in intro:
                intro[f] = sha
    return intro


def introducing_commit_map(project_root: Path, rel_paths: list[str]) -> dict[str, list[str]]:
    """Map each test file → its introducing commit's ``affected_frs`` (signal d).

    Matches with prefix tolerance because events sometimes store a short sha.
    """
    events = _load_events_fr_by_commit(project_root)
    if not events:
        return {}
    out: dict[str, list[str]] = {}
    for rel_path, sha in _file_introducing_commits(project_root, set(rel_paths)).items():
        frs: set[str] = set()
        for ev_commit, ev_frs in events.items():
            if sha.startswith(ev_commit) or ev_commit.startswith(sha):
                frs.update(ev_frs)
        if frs:
            out[rel_path] = sorted(frs)
    return out


__all__ = [
    "FR", "TestRecord", "detect_layer", "split_of_path", "path_fr_tokens",
    "iter_test_files", "scan_tests", "parse_frs", "introducing_commit_map",
]
