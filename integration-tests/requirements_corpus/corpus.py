"""Materialize a corpus fixture into a real project root.

The corpus is written to disk at test time rather than committed as an on-disk
tree. A committed ``integration-tests/fixtures/**/.shipwright/planning/*/spec.md``
tree would be walked by this repo's OWN requirements machinery -- the
traceability collector, the artifact-path-canon gate, staleness checks. A test
corpus that pollutes the control plane it measures is a self-inflicted false
verdict.

Files are written, not passed as strings, because ``rtm.collect_requirements``
takes a project root and performs its own walk -- it cannot be string-driven.
Real files give one corpus for both the discovery and the parser dimension and
exercise discovery+parse together, as production does.
"""

from __future__ import annotations

from pathlib import Path

from .corpus_data import DIR, FILE, FIXTURES


class CorpusError(RuntimeError):
    """A fixture is malformed -- refuse to materialize it."""


def _safe_target(root: Path, rel: str) -> Path:
    """Resolve *rel* under *root*, refusing anything that escapes it.

    The corpus deliberately contains unusual filesystem shapes, so the writer
    must not be the thing that turns a fixture edit into a write outside
    ``tmp_path``.
    """
    if not rel or rel != rel.strip():
        raise CorpusError(f"fixture path is empty or padded: {rel!r}")
    candidate = Path(rel)
    if candidate.is_absolute() or candidate.drive or candidate.anchor:
        raise CorpusError(f"fixture path must be relative: {rel!r}")
    if ".." in candidate.parts:
        raise CorpusError(f"fixture path escapes the corpus root: {rel!r}")
    target = (root / candidate).resolve()
    root_resolved = root.resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise CorpusError(f"fixture path escapes the corpus root: {rel!r}")
    return target


def materialize(fixture: str, root: Path) -> Path:
    """Write *fixture* under *root* and return *root*.

    Longest paths are written first so that a ``FILE`` sentinel standing in for
    a directory cannot be clobbered by a later nested write, and so a nested
    write cannot silently turn a ``FILE`` sentinel into a directory.
    """
    if fixture not in FIXTURES:
        raise CorpusError(
            f"unknown fixture {fixture!r}; known: {sorted(FIXTURES)}"
        )
    root.mkdir(parents=True, exist_ok=True)

    entries = FIXTURES[fixture]
    # Directories and plain files first, sentinels last: a FILE sentinel must
    # win over any parent directory a sibling entry would have created.
    ordered = sorted(entries.items(), key=lambda kv: (kv[1] == FILE, kv[0]))

    for rel, content in ordered:
        target = _safe_target(root, rel)
        if content == DIR:
            target.mkdir(parents=True, exist_ok=True)
            continue
        if content == FILE:
            if target.is_dir():
                raise CorpusError(
                    f"{rel!r} is declared FILE but a directory already exists "
                    "there -- fixture entries collide"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("not a directory\n", encoding="utf-8")
            continue
        if target.exists() and target.is_dir():
            raise CorpusError(f"{rel!r} collides with an existing directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        # encoding is explicit: a bare write_text defaults to cp1252 on Windows
        # runners and would alter the bytes the parsers see.
        target.write_text(content, encoding="utf-8")

    return root


def spec_paths(fixture: str) -> list[str]:
    """Every ``spec.md``-ish path a fixture declares, in declaration order.

    Used by the parser dimension, which needs a concrete file to read rather
    than a project root to walk.
    """
    out = []
    for rel, content in FIXTURES[fixture].items():
        if content in (DIR, FILE):
            continue
        if rel.endswith(".md"):
            out.append(rel)
    return sorted(out)
