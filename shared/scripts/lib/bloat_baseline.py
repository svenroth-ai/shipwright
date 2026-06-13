"""Single producer for the bloat-allowlist schema + classification.

Consumed by Phase-0 / adopt baseline_generator (writers),
check_file_size.py (classify + limit), and bloat_gate_on_stop.py
(reader). Centralising the schema + classification here prevents
producer/consumer drift. check_file_size.py keeps thin delegating
wrappers so legacy call sites stay stable.

Schema (``<project_root>/shipwright_bloat_baseline.json``):

    {"version": 1, "entries": [
        {"path": "plugins/foo/bar.py", "limit": 300, "current": 412,
         "state": "grandfathered", "adr": null}
    ]}

Paths are normalised to forward-slash POSIX form by ``normalize_path``
on both write and read so producer and consumer cannot drift. ``load``
returns ``None`` on any malformed-input condition (missing file, bad
JSON, non-list ``entries``) + one stderr diagnostic — fail-open by
design so a corrupt baseline never bricks the Stop hook.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable

# atomic_write is a sibling module in this same dir; insert it so the import
# resolves whether bloat_baseline was loaded as ``lib.bloat_baseline`` (shared/
# scripts on path) or as a top-level ``bloat_baseline`` (shared/scripts/lib on
# path) — mirrors the unique-top-level-name pattern of ``file_lock``.
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from atomic_write import durable_atomic_write  # noqa: E402

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

BASELINE_FILENAME = "shipwright_bloat_baseline.json"
MARKER_TTL_SECONDS = 3600  # 1 hour — campaign §5.2

LIMIT_RUNTIME_PROMPT = 400
LIMIT_SOURCE = 300

# Source / test extensions where the 300-LOC limit applies.
_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}

# Skip globs / substrings — generated, vendored, lock files, migrations,
# test fixtures (spec §3.2: long-by-nature, exempt from size check).
# ``.shipwright/runs/`` is the gitignored runtime-artifact tree (campaign
# setup scripts, surface_verification logs, evidence files); scanning it
# produces false-positive Group H1 findings because the content can never
# be committed.
_SKIP_PATH_RE = re.compile(
    r"(\.lock$|package-lock|node_modules[/\\]|vendor[/\\]|dist[/\\]"
    r"|build[/\\]|\.min\.|__pycache__|\.pyc$|\.generated\."
    r"|migrations?[/\\].*\.sql"
    r"|(?:^|[/\\])fixtures[/\\]"
    r"|(?:^|[/\\])__fixtures__[/\\]"
    r"|(?:^|[/\\])\.shipwright[/\\]runs[/\\])",
    re.IGNORECASE,
)
# Non-source extensions that are never weighed.
_SKIP_EXT_RE = re.compile(
    r"\.(ya?ml|json|toml|csv|svg|xml|html|css)$",
    re.IGNORECASE,
)

# Runtime-prompt path patterns.
# Matched against POSIX-normalised paths.
_RUNTIME_BASENAMES = {"SKILL.md", "CLAUDE.md"}
_RUNTIME_PATH_PATTERNS = (
    re.compile(r"(?:^|/)plugins/[^/]+/agents/[^/]+\.md$", re.IGNORECASE),
    re.compile(r"(?:^|/)shared/prompts/[^/]+\.md$", re.IGNORECASE),
)


# ---------------------------------------------------------------------
# Path normalisation
# ---------------------------------------------------------------------

def normalize_path(p: str) -> str:
    """POSIX-normalise ``p``; idempotent; no case-folding (git is case-tracking)."""
    if not p:
        return p
    s = p.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


_WORKTREE_PREFIX_RE = re.compile(r"^\.worktrees/[^/]+/")


def strip_worktree_prefix(rel_path: str) -> str:
    """Strip a leading ``.worktrees/<slug>/`` so a marker path recorded relative
    to the MAIN root during a ``/shipwright-iterate`` run resolves against the
    repo-relative baseline keys (idempotent for ordinary paths). trg-305e2aab:
    without it, a worktree iterate growing an already-baselined file is
    mis-classified ``crossing`` + false-blocks the Stop gate."""
    return _WORKTREE_PREFIX_RE.sub("", normalize_path(rel_path), count=1)


# ---------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------

def classify_md(path: str) -> str | None:
    """``runtime-prompt`` for SKILL.md/CLAUDE.md/plugins-agents/shared-prompts;
    ``doc`` for other ``.md``; ``None`` otherwise."""
    if not path.lower().endswith(".md"):
        return None
    norm = normalize_path(path)
    basename = norm.rsplit("/", 1)[-1]
    if basename in _RUNTIME_BASENAMES:
        return "runtime-prompt"
    for pattern in _RUNTIME_PATH_PATTERNS:
        if pattern.search(norm):
            return "runtime-prompt"
    return "doc"


def limit_for(path: str) -> int | None:
    """Runtime-prompts → 400; source/test → 300; else ``None``.
    Caller still consults :func:`should_skip` for path-based exclusions."""
    md = classify_md(path)
    if md == "runtime-prompt":
        return LIMIT_RUNTIME_PROMPT
    if md == "doc":
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext in _SOURCE_EXTS:
        return LIMIT_SOURCE
    return None


def should_skip(path: str) -> bool:
    """True for lock files, vendored, dist/build, generated, migrations,
    plain markdown docs, and data extensions (JSON/YAML/TOML/…).

    Runtime-prompt classification takes precedence over path-based
    skips — a ``skills/build/SKILL.md`` file is a runtime prompt even
    though it contains the substring ``build/``.
    """
    md = classify_md(path)
    if md == "runtime-prompt":
        return False
    if md == "doc":
        return True
    if _SKIP_PATH_RE.search(path):
        return True
    if _SKIP_EXT_RE.search(path):
        return True
    ext = os.path.splitext(path)[1].lower()
    if ext in _SOURCE_EXTS:
        return False
    # Unknown extension — skip by default (no defined limit).
    return True


# ---------------------------------------------------------------------
# Scan — enumerate oversize tracked files under ``project_root``
# ---------------------------------------------------------------------

def _file_newlines(path: Path) -> int:
    try:
        with path.open("rb") as fh:
            return fh.read().count(b"\n")
    except OSError:
        return 0


def _iter_candidates(project_root: Path) -> Iterable[Path]:
    """Walk ``project_root`` for candidate files, skipping noisy dirs.

    ``dist`` / ``build`` are only pruned when they are direct children
    of the project root (i.e. tool output dirs), never when nested
    (``skills/build/`` is a real source path).
    """
    skip_anywhere = {
        ".git", "node_modules", ".venv", "venv", "__pycache__",
        ".pytest_cache", ".ruff_cache", ".mypy_cache",
        ".worktrees", ".shipwright-webui",
    }
    skip_at_root_only = {"dist", "build"}
    root = project_root.resolve()
    for dirpath, dirnames, filenames in os.walk(project_root):
        cur = Path(dirpath).resolve()
        at_root = cur == root
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_anywhere
            and not (at_root and d in skip_at_root_only)
        ]
        for name in filenames:
            yield Path(dirpath) / name


def scan(project_root: Path | str) -> list[dict]:
    """Return sorted oversize-file entries (one dict per offender).
    Each dict: ``path`` (POSIX, project-relative), ``limit``, ``current``,
    ``state="grandfathered"``, ``adr=None``."""
    root = Path(project_root).resolve()
    entries: list[dict] = []
    for path in _iter_candidates(root):
        try:
            rel = path.resolve().relative_to(root)
        except ValueError:
            continue
        rel_str = normalize_path(str(rel))
        if should_skip(rel_str):
            continue
        limit = limit_for(rel_str)
        if limit is None:
            continue
        current = _file_newlines(path)
        if current <= limit:
            continue
        entries.append({
            "path": rel_str,
            "limit": limit,
            "current": current,
            "state": "grandfathered",
            "adr": None,
        })
    entries.sort(key=lambda e: e["path"])
    return entries


# ---------------------------------------------------------------------
# Baseline file I/O
# ---------------------------------------------------------------------

def _baseline_path(project_root: Path | str) -> Path:
    return Path(project_root) / BASELINE_FILENAME


def write_baseline(project_root: Path | str, doc: dict) -> Path:
    """Atomically + durably write the baseline (tmp + fsync + os.replace via the
    shared :func:`durable_atomic_write`). Returns the written path."""
    target = _baseline_path(project_root)
    durable_atomic_write(target, json.dumps(doc, indent=2, sort_keys=False) + "\n")
    return target


def load(project_root: Path | str) -> dict | None:
    """Load baseline; ``None`` on missing / malformed (fail-open with stderr
    diagnostic on malformed). On success, ``entries[*].path`` is
    POSIX-normalised so callers can compare against marker paths."""
    target = _baseline_path(project_root)
    if not target.is_file():
        return None
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"bloat_baseline: read failed ({exc!r}) — fail-open",
            file=sys.stderr,
        )
        return None
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(
            f"bloat_baseline: malformed JSON ({exc.msg}) — fail-open",
            file=sys.stderr,
        )
        return None
    if not isinstance(doc, dict):
        print("bloat_baseline: root not an object — fail-open", file=sys.stderr)
        return None
    entries = doc.get("entries")
    if not isinstance(entries, list):
        print(
            "bloat_baseline: entries is not a list — fail-open",
            file=sys.stderr,
        )
        return None
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            entry["path"] = normalize_path(entry["path"])
    return doc
