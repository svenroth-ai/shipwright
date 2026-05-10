"""TODO/FIXME inventory for adopted projects.

Inline drift markers (`TODO`, `FIXME`, `HACK`, `XXX`, `DEPRECATED`) are
exactly what /shipwright-iterate users grep for as their first step
after onboarding. Pre-compute the inventory at adopt time — operators
expect the file to exist whether or not markers were found.

Output: `.shipwright/agent_docs/known_issues.md` with:

- A summary table at the top (marker → count).
- One section per marker type, listing file:line and the marker text
  (truncated to 200 characters per bullet).
- Cap at 200 entries total; beyond that, top 50 are shown and the rest
  are summarized as counts.

Implementation: regex over source files, with deterministic skip rules
for common artifact directories (node_modules, dist, build, vendor) and
a `git check-ignore` consult for project-specific gitignore rules. When
git is unavailable we fall back to the skip-list — best-effort.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

AGENT_DOCS_DIR = ".shipwright/agent_docs"
OUTPUT_REL = f"{AGENT_DOCS_DIR}/known_issues.md"
TOTAL_CAP = 200
TOP_N_WHEN_TRUNCATED = 50
PER_BULLET_CHAR_CAP = 200

_MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX|DEPRECATED)\b:?\s*(.*)")
_MARKERS = ("TODO", "FIXME", "HACK", "XXX", "DEPRECATED")

# Recognised comment-opener forms that may precede a marker on the same line.
# The pattern is anchored at end-of-prefix so it works for both leading-
# position comments (`# TODO`) AND inline comments after code
# (`x = 1  # TODO`). The `(?:^|\s)` boundary prevents partial matches inside
# identifiers or numeric literals.
#
#   #            Python / shell / Ruby line comment
#   //           JS / TS / Java / Go / Rust line comment
#   /*           C-style block-comment opener (single-line form `/* TODO */`)
#   <!--         HTML / XML comment opener
#
# SQL/Lua/Haskell `--` is intentionally NOT here because no `.sql`/`.lua`/`.hs`
# extension is in `_SOURCE_SUFFIXES`. Markdown headings (`#`) and bare
# `--- TODO` horizontal rules are also intentionally rejected.
_COMMENT_CONTEXT_RE = re.compile(r"(?:^|\s)(?:#|//|/\*+|<!--)\s*$")

# JSDoc / Javadoc continuation line: `^\s*\*\s*` (asterisk anchored at start
# of line). Inline `*` is NOT a JSDoc continuation — it is almost always
# multiplication (`a * b`), so the asterisk branch must not be combined with
# the inline-comment recogniser above.
_JSDOC_CONTINUATION_RE = re.compile(r"^\s*\*\s*$")

# Markdown list bullet at start of line: `^\s*-\s+`. Strict single-dash form
# rejects horizontal rules (`---`) and dash sequences from the predicate.
_MARKDOWN_BULLET_RE = re.compile(r"^\s*-\s+$")

# Limitation (documented, accepted as out-of-scope): markers inside multi-line
# block comments where the marker line itself has only whitespace prefix (no
# leading `*` continuation) are NOT detected — the predicate is line-local
# and cannot see the `/*` opener on a previous line. Authors using this style
# should add a `*` continuation per JSDoc convention.

_SOURCE_SUFFIXES = (
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".kt",
    ".cs",
    ".cpp", ".cc", ".c", ".h", ".hpp",
    ".swift",
    ".php",
    ".css", ".scss", ".sass",
    ".html",
    ".vue", ".svelte", ".astro",
)

# Hard-skip these directory names anywhere in the path. .gitignore handles
# project-specific cases; this is the universally-noisy floor that should
# always be excluded even when not gitignored.
_SKIP_DIRS = {
    "node_modules", "dist", "build", "out", ".next", ".nuxt", ".turbo",
    "vendor", "target", "__pycache__", ".venv", "venv", ".tox",
    "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".git", ".shipwright",  # adopt's own outputs; recursion guard
}


def _is_skipped_path(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    return any(p in _SKIP_DIRS for p in parts)


# Hardcoded fallback (used when `Path(__file__).relative_to(project_root)`
# raises — i.e. the scanner is invoked from outside its source tree). The
# dynamic resolution in `_self_reference_skip()` below is the primary
# defence; this constant covers the edge case.
_SELF_REFERENCE_FALLBACK = (
    "plugins/shipwright-adopt/scripts/lib/known_issues_inventory.py"
)


def _self_reference_skip(project_root: Path) -> set[str]:
    """Return the relative path of this scanner module under project_root,
    so it is excluded from the scan. The scanner's own source by definition
    contains the marker tuple as data, plus regex literals and rendered
    output strings — every match against itself is a false positive.
    """
    try:
        rel = Path(__file__).resolve().relative_to(project_root.resolve()).as_posix()
        return {rel}
    except ValueError:
        # __file__ is outside project_root (e.g. tests using tmp_path).
        # The hardcoded fallback handles repos that mirror the canonical
        # source layout; tests that don't mirror it correctly produce no
        # match and the test fixture path is responsible for skip behaviour.
        return {_SELF_REFERENCE_FALLBACK}


def _is_marker_in_comment_context(line: str, match_start: int) -> bool:
    """Return True if the marker at ``match_start`` is in a recognised
    comment context.

    Three acceptance forms:
    1. The line prefix (before ``match_start``) ends with a comment opener
       — see ``_COMMENT_CONTEXT_RE``. Covers both leading-position comments
       (`# TODO`) and inline comments after code (`x = 1  # TODO`).
    2. The line prefix is a JSDoc / Javadoc continuation (`^\\s*\\*\\s*`).
       Asterisk is anchored at start of line; inline `*` between code
       tokens (`a * b TODO`) is rejected because it is multiplication,
       not a comment context.
    3. The line prefix is a markdown list bullet (`^\\s*-\\s+`). Covers
       single-dash bullets in source-embedded markdown (e.g. inside Vue /
       Svelte / Astro template strings). Triple-dash horizontal rules are
       rejected because they require `\\s+` after the dash, which fails on
       `---`.
    """
    prefix = line[:match_start]
    if _COMMENT_CONTEXT_RE.search(prefix):
        return True
    if _JSDOC_CONTINUATION_RE.match(prefix):
        return True
    if _MARKDOWN_BULLET_RE.match(prefix):
        return True
    return False


def _is_test_fixture_path(rel: str) -> bool:
    """Iterate 2 Sub-2B: heuristic for test-shaped paths whose markers are
    almost always test inputs, not real workflow TODOs.

    Default-skipped unless caller passes scan_tests=True. The 2026-05-02
    self-adoption found 22 of 28 markers came from
    plugins/shipwright-adopt/tests/test_known_issues_inventory.py fixtures.
    A broad grep over plugins/*/tests/ confirmed 0 real workflow TODOs in
    plugin test directories at the time, so default-skip is safe. Repos
    that legitimately track TODOs in tests can opt back in via
    `--scan-tests` / `scan_tests=True`.
    """
    rel_posix = rel.replace("\\", "/")
    parts = rel_posix.split("/")
    if "tests" in parts:
        return True
    name = parts[-1]
    stem, _, ext = name.rpartition(".")
    if not stem:
        return False
    # Python: test_*.py, *_test.py
    if ext == "py" and (stem.startswith("test_") or stem.endswith("_test")):
        return True
    # JS/TS: *.test.ts, *.test.tsx, *.spec.ts, *.spec.tsx, *.test.js, *.spec.js
    if ext in {"ts", "tsx", "js", "jsx"} and (
        stem.endswith(".test") or stem.endswith(".spec")
    ):
        return True
    return False


def _gitignore_filter(project_root: Path, rel_paths: list[str]) -> set[str]:
    """Return the set of rel_paths that git check-ignore says are ignored.

    We invoke `check-ignore -z --stdin` to bypass Windows-style line-
    ending quoting (without `-z`, git wraps any path containing CR/LF in
    quotes, which breaks string-equality matching). Best-effort: if git
    is unavailable or the call fails, return an empty set (the skip-list
    above still excludes the universal noise)."""
    if not rel_paths:
        return set()
    try:
        r = subprocess.run(
            ["git", "-C", str(project_root), "check-ignore", "-z", "--stdin"],
            input=("\0".join(rel_paths) + "\0").encode("utf-8"),
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return set()
    if r.returncode not in (0, 1):
        return set()
    raw = r.stdout.decode("utf-8", errors="ignore")
    return {p for p in raw.split("\0") if p}


def _collect_source_files(
    project_root: Path,
    *,
    scan_tests: bool = False,
) -> list[Path]:
    """Walk project_root and return source files worth scanning.

    When ``scan_tests`` is False (default), test-shaped paths
    (`tests/`-anywhere, `test_*.py`, `*_test.py`, `*.test.ts`/`*.spec.ts`
    and `tsx`/`js`/`jsx` siblings) are skipped — see `_is_test_fixture_path`
    rationale.

    Always skips this scanner's own source file (`_self_reference_skip`)
    because its source by definition contains the marker tuple, regex
    literals, and rendered output strings — every match against itself is
    a false positive.
    """
    self_skip = _self_reference_skip(project_root)
    out: list[Path] = []
    for child in project_root.rglob("*"):
        if not child.is_file():
            continue
        if child.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        try:
            rel = child.relative_to(project_root).as_posix()
        except ValueError:
            continue
        if _is_skipped_path(rel):
            continue
        if not scan_tests and _is_test_fixture_path(rel):
            continue
        if rel in self_skip:
            continue
        out.append(child)
    return out


def _scan_file(path: Path, rel: str) -> list[dict[str, Any]]:
    """Return marker entries from a single file.

    A marker is only counted when it appears in a recognised comment
    context (see ``_is_marker_in_comment_context``). Bare marker strings
    in source code (regex literals, tuple elements, rendered output) are
    rejected — they were the dominant false-positive source pre-fix.
    """
    try:
        body = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for lineno, line in enumerate(body.splitlines(), start=1):
        m = _MARKER_RE.search(line)
        if not m:
            continue
        if not _is_marker_in_comment_context(line, m.start()):
            continue
        marker = m.group(1)
        text = (m.group(2) or "").strip()
        if len(text) > PER_BULLET_CHAR_CAP:
            text = text[:PER_BULLET_CHAR_CAP].rstrip() + "…"
        entries.append({
            "marker": marker,
            "file": rel,
            "line": lineno,
            "text": text,
        })
    return entries


def _render_md(
    entries_by_marker: dict[str, list[dict[str, Any]]],
    total: int,
    truncated: bool,
) -> str:
    if total == 0:
        return (
            "# Known Issues — TODO / FIXME inventory\n\n"
            "_Auto-generated by /shipwright-adopt. Re-runs refresh this file._\n\n"
            "**No TODO / FIXME / HACK / XXX / DEPRECATED markers found in the source.**\n\n"
            "Refresh this file by re-running adopt or by editing it manually as the "
            "codebase accumulates inline drift markers.\n"
        )

    counts = {m: len(entries_by_marker.get(m, [])) for m in _MARKERS}
    summary_rows = "\n".join(
        f"| {m} | {counts[m]} |" for m in _MARKERS if counts[m]
    )
    body = (
        "# Known Issues — TODO / FIXME inventory\n\n"
        "_Auto-generated by /shipwright-adopt. Re-runs refresh this file. "
        "Lift items into iterate specs or close them out as you go._\n\n"
        "## Summary\n\n"
        "| Marker | Count |\n"
        "|--------|-------|\n"
        f"{summary_rows}\n"
        f"\n_Total: {total} marker(s)._"
    )
    if truncated:
        body += (
            f"\n\n_Truncated: showing the first {TOP_N_WHEN_TRUNCATED} bullets per "
            f"marker type below. Full set lives in source — re-run a `grep -nR` "
            "to walk it._"
        )
    body += "\n\n"

    for marker in _MARKERS:
        items = entries_by_marker.get(marker, [])
        if not items:
            continue
        body += f"## {marker}\n\n"
        shown = items[:TOP_N_WHEN_TRUNCATED] if truncated else items
        for entry in shown:
            txt = entry["text"] or "_(no text)_"
            body += f"- `{entry['file']}:{entry['line']}` — {txt}\n"
        if truncated and len(items) > len(shown):
            body += (
                f"- _… and {len(items) - len(shown)} more {marker} marker(s) "
                "in source (not listed)._\n"
            )
        body += "\n"
    return body


def write_known_issues_inventory(
    project_root: Path,
    *,
    scan_tests: bool = False,
) -> dict[str, Any]:
    """Walk source files, collect markers, write known_issues.md.

    Returns a result dict useful for the SKILL.md handoff. Pass
    ``scan_tests=True`` to include test-fixture paths (see
    ``_is_test_fixture_path``) that are skipped by default.
    """
    files = _collect_source_files(project_root, scan_tests=scan_tests)
    rel_paths = [f.relative_to(project_root).as_posix() for f in files]
    ignored = _gitignore_filter(project_root, rel_paths)

    entries_by_marker: dict[str, list[dict[str, Any]]] = {m: [] for m in _MARKERS}
    total = 0
    for f, rel in zip(files, rel_paths):
        if rel in ignored:
            continue
        for entry in _scan_file(f, rel):
            entries_by_marker[entry["marker"]].append(entry)
            total += 1

    truncated = total > TOTAL_CAP

    out_path = project_root / OUTPUT_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _render_md(entries_by_marker, total, truncated),
        encoding="utf-8",
    )

    return {
        "path": out_path,
        "total": total,
        "entries": total,
        "truncated": truncated,
        "by_marker": {m: len(v) for m, v in entries_by_marker.items()},
    }
