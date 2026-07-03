"""repo_context — one memoized, capped snapshot of a repository.

``RepoContext`` is built **once** from a :class:`ResolvedTarget` and shared by
every downstream reader (projector, routing, renderers): the file list, git
head, detector outputs and synthetic events are computed a single time — no
N+1 filesystem/git traversal (GPT #8).

Determinism & safety (plan §6): fixed caps (max commits / files / bytes-per-file)
with deterministic truncation order (newest-N commits from ``git log``,
lexicographic file traversal — no ad-hoc sampling). Traversal stays within the
resolved root and never follows symlinks out of it; ``read_text`` re-checks that
a resolved path is inside the root before reading.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from detectors_bridge import detect_all
from git_exec import run_git
from resolve_target import ResolvedTarget
from synthetic_projection import WorkEvent, collect_events

# The reused adopt detectors scan at most this many source files before an
# (order-dependent) truncation; beyond it, feature inference is a *sample*, so
# the grader labels requirement-traceability provenance truncated/sampled.
_DETECTOR_PY_CAP = 500
_DETECTOR_WEB_CAP = 200
_SOURCE_EXTS = (".py",)
_WEB_EXTS = (".ts", ".tsx", ".js", ".jsx")

# Directories that never carry gradeable signal — pruned from the file list to
# keep it bounded and meaningful (detectors do their own scoped scans).
_PRUNE_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build", ".next", ".turbo",
    "coverage", ".idea", ".vscode", "vendor", "target",
})

_TEST_SUFFIXES = (".test.ts", ".test.tsx", ".test.js", ".test.jsx",
                  ".spec.ts", ".spec.tsx", ".spec.js")


@dataclass(frozen=True)
class Caps:
    max_commits: int = 500
    max_files: int = 5000
    max_bytes_per_file: int = 1_000_000


DEFAULT_CAPS = Caps()


def _is_test_file(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py") or name.endswith("_test.go"):
        return True
    if name.endswith("_spec.rb"):
        return True
    if any(name.endswith(sfx) for sfx in _TEST_SUFFIXES):
        return True
    # A file living under a top-level tests/ or test/ directory.
    parts = rel.split("/")
    return any(p in ("tests", "test", "__tests__") for p in parts[:-1])


class RepoContext:
    """A single, memoized snapshot of a resolved repository."""

    def __init__(self, target: ResolvedTarget, *, caps: Caps = DEFAULT_CAPS) -> None:
        self.target = target
        self.root = target.local_path
        self.caps = caps

        self.files, self.truncated_files = self._walk_files()
        self.test_files = [f for f in self.files if _is_test_file(f)]
        self.test_file_count = len(self.test_files)

        detected = detect_all(self.root)
        self.stack: dict[str, Any] = detected["stack"]
        self.test_frameworks: dict[str, Any] = detected["test_frameworks"]
        self.features: list[dict[str, Any]] = detected["features"]
        self.ci: dict[str, Any] = detected["ci"]
        self.has_ci = bool(self.ci.get("provider"))
        self.primary_language = str(self.stack.get("primary_language", "unknown"))

        all_events = collect_events(self.root, max_commits=caps.max_commits)
        self.events: list[WorkEvent] = all_events
        self.events_truncated = len(all_events) >= caps.max_commits
        self.head_sha = self._git_head()
        self.features_truncated = self._features_truncated()

    def _features_truncated(self) -> bool:
        """True when feature inference sampled (repo exceeds the detector caps).

        Honest determinism label: within the caps the feature set is complete
        (order-independent); beyond them the reused detector truncates in
        filesystem order, so requirement-traceability is a labelled sample.
        """
        py = sum(1 for f in self.files if f.endswith(_SOURCE_EXTS))
        web = sum(1 for f in self.files if f.endswith(_WEB_EXTS))
        return self.truncated_files or py > _DETECTOR_PY_CAP or web > _DETECTOR_WEB_CAP

    def _walk_files(self) -> tuple[list[str], bool]:
        """Lexicographic, capped, within-root file list (no symlink dirs).

        Bounded: traversal stops once the cap is exceeded (deterministic sorted
        DFS), so a hostile/huge tree cannot exhaust the budget.
        """
        collected: list[str] = []
        root = self.root
        limit = self.caps.max_files
        truncated = False
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in _PRUNE_DIRS)
            for name in sorted(filenames):
                full = Path(dirpath) / name
                try:
                    rel = full.relative_to(root).as_posix()
                except ValueError:
                    continue
                collected.append(rel)
            if len(collected) > limit:
                truncated = True
                break
        collected.sort()
        return collected[:limit], truncated

    def _git_head(self) -> str:
        rc, out = run_git(["rev-parse", "HEAD"], self.root, timeout=10)
        return out.strip() if rc == 0 else ""

    def read_text(self, rel: str, *, max_bytes: int | None = None) -> str:
        """Read a repo-relative file, bounded and within-root. '' on any issue."""
        limit = max_bytes if max_bytes is not None else self.caps.max_bytes_per_file
        try:
            full = (self.root / rel).resolve()
            full.relative_to(self.root.resolve())  # symlink-escape guard
        except (ValueError, OSError, RuntimeError):
            return ""
        if not full.is_file():
            return ""
        try:
            with full.open("r", encoding="utf-8", errors="replace") as fh:
                return fh.read(limit)
        except OSError:
            return ""
