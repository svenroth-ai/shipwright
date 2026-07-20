"""Shared parsers for drift detection and spec/ADR coherence.

Iterate 12.0 extracts these pure-function parsers out of
`shared/scripts/hooks/check_drift.py` and the compliance
`data_collector.py` so that:

- `check_drift.py` (SessionStart hook) stays a thin I/O wrapper that imports
  its parsing logic from here;
- `shared/scripts/tools/verifiers/*_checks.py` (iterate 12.1+) can reuse
  the same Structure-block, command-block, FR-table and ADR-header parsers
  without duplicating regex state;
- the planned `shipwright-check` detective audit
  (see Spec/shipwright-check-plan.md) can reuse the drift primitives
  instead of cannibalising the hook.

Everything in this module is PURE: no side effects, no globals, no
exit-code semantics. Callers decide what to do with findings.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


def _discovery():
    # Sibling loaded by FILE LOCATION, not ``from lib.planning_discovery``: this
    # module is itself location-loaded by audit/audit_adapters (group_a/d/g), and
    # group_d calls collect_requirements_from_planning THROUGH that load, where no
    # ``lib`` package is bound and a package import would raise (ADR-045).
    name = "_shipwright_planning_discovery"
    if (mod := sys.modules.get(name)) is None:
        import importlib.util as _u
        spec = _u.spec_from_file_location(name, Path(__file__).with_name("planning_discovery.py"))
        sys.modules[name] = mod = _u.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# CLAUDE.md Structure block
# ---------------------------------------------------------------------------

# One Structure-block line: optional indent, identifier (optionally with
# trailing slash for dirs), optional `# comment`.
_STRUCT_ENTRY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<name>[\w.-]+)(?P<slash>/?)\s*(?:#.*)?$"
)

# Fenced code block following "## Structure" or "### Structure".
_STRUCTURE_BLOCK_RE = re.compile(
    r"#{2,3}\s+Structure\s*\n+```[^\n]*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def extract_structure_block(content: str) -> str | None:
    """Return the inner text of the first Structure code block, or None."""
    m = _STRUCTURE_BLOCK_RE.search(content)
    return m.group(1) if m else None


def parse_structure_entries(block: str) -> list[tuple[int, str, bool]]:
    """Return `(indent, name, is_dir)` for each recognizable entry in a
    Structure block. Comment-only lines and obvious non-entries are
    skipped. Indent is the raw character count (used later to reconstruct
    the parent chain via `build_paths_from_entries`)."""
    entries: list[tuple[int, str, bool]] = []
    for line in block.splitlines():
        if not line.strip():
            continue
        m = _STRUCT_ENTRY_RE.match(line)
        if not m:
            continue
        name = m.group("name")
        if name.startswith("_") and name.endswith("_"):
            continue
        entries.append((len(m.group("indent")), name, bool(m.group("slash"))))
    return entries


def build_paths_from_entries(
    entries: list[tuple[int, str, bool]],
) -> list[tuple[str, bool]]:
    """Resolve each entry into a POSIX-style relative path.

    Uses indent levels to reconstruct the parent chain. Returns a list of
    `(relative_path, is_dir)` in the original order.
    """
    stack: list[tuple[int, str]] = []
    out: list[tuple[str, bool]] = []
    for indent, name, is_dir in entries:
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1] if stack else ""
        path = f"{parent}/{name}" if parent else name
        stack.append((indent, path))
        out.append((path, is_dir))
    return out


# ---------------------------------------------------------------------------
# .gitignore + hidden dirs
# ---------------------------------------------------------------------------

# Hidden/ignored directory names that should never surface as
# "undocumented" findings. Two categories:
#  - Build/test/IDE artifacts: node_modules, .venv, dist, etc.
#  - Shipwright runtime artifacts of target projects: .shipwright/agent_docs,
#    .shipwright/designs, .shipwright/planning, compliance, plus the
#    ``.shipwright/`` umbrella. These are state, not architecture; CLAUDE.md
#    in a target project should NOT be forced to enumerate them. The legacy
#    top-level dirnames (``planning``, ``designs``, ``agent_docs``) stay here
#    for backwards-compat with projects that haven't run the migration yet.
HIDDEN_DIR_DEFAULTS: frozenset[str] = frozenset({
    "node_modules", "__pycache__", "dist", "build", ".venv", ".git",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".idea", ".vscode",
    "vendor", "e2e-results", "playwright-report", "test-results",
    "agent_docs",  # artifact-path-canon: legacy (post-migration tolerance)
    "compliance",  # artifact-path-canon: legacy (post-migration tolerance)
    "designs",  # artifact-path-canon: legacy (post-migration tolerance)
    ".shipwright",  # canonical umbrella for post-migration artifacts
    "planning",  # artifact-path-canon: legacy (post-migration tolerance)
})


def load_gitignore(root: str | os.PathLike[str]) -> set[str]:
    """Return the set of simple top-level names ignored by ``.gitignore``.

    Only handles plain `name/` or `name` entries at the root level — enough
    to filter common drift noise without emulating full gitignore semantics.
    Patterns with wildcards are ignored.
    """
    ignored: set[str] = set()
    gi = os.path.join(str(root), ".gitignore")
    if not os.path.exists(gi):
        return ignored
    try:
        with open(gi, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                line = line.lstrip("/").rstrip("/")
                if any(ch in line for ch in "*?[]"):
                    continue
                ignored.add(line)
    except OSError:
        pass
    return ignored


# ---------------------------------------------------------------------------
# Development command blocks
# ---------------------------------------------------------------------------

_DEV_BLOCK_RE = re.compile(
    r"#{2,3}\s+Development\b.*?```bash\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)

# "npm run <script>" with optional "cd <dir> && " prefix.
_NPM_RUN_RE = re.compile(
    r"(?:cd\s+(?P<cd>[\w./-]+)\s*&&\s*)?npm\s+run\s+(?P<script>[\w:-]+)"
)

# "uv run <script>" (positional tool, not a pyproject entry) — surfaced
# so future verifiers can assert the referenced script exists.
_UV_RUN_RE = re.compile(
    r"(?:cd\s+(?P<cd>[\w./-]+)\s*&&\s*)?uv\s+run\s+(?P<tool>[\w./-]+)"
)

# "make <target>" invocations.
_MAKE_RE = re.compile(
    r"(?:cd\s+(?P<cd>[\w./-]+)\s*&&\s*)?make\s+(?P<target>[\w:-]+)"
)


def extract_dev_blocks(content: str) -> list[str]:
    """Return the inner text of every ``## Development`` bash code block."""
    return _DEV_BLOCK_RE.findall(content)


@dataclass(frozen=True)
class NpmRunRef:
    cd_target: str | None
    script: str


@dataclass(frozen=True)
class UvRunRef:
    cd_target: str | None
    tool: str


@dataclass(frozen=True)
class MakeRef:
    cd_target: str | None
    target: str


def parse_npm_run_refs(block: str) -> list[NpmRunRef]:
    """Parse ``npm run`` references from a single Development block."""
    return [
        NpmRunRef(cd_target=m.group("cd"), script=m.group("script"))
        for m in _NPM_RUN_RE.finditer(block)
    ]


def parse_uv_run_refs(block: str) -> list[UvRunRef]:
    """Parse ``uv run`` references from a single Development block."""
    return [
        UvRunRef(cd_target=m.group("cd"), tool=m.group("tool"))
        for m in _UV_RUN_RE.finditer(block)
    ]


def parse_make_refs(block: str) -> list[MakeRef]:
    """Parse ``make <target>`` references from a single Development block."""
    return [
        MakeRef(cd_target=m.group("cd"), target=m.group("target"))
        for m in _MAKE_RE.finditer(block)
    ]


def find_nearest_package_json(
    start_dir: str | os.PathLike[str],
    stop_at: str | os.PathLike[str],
) -> str | None:
    """Walk up from ``start_dir`` until a package.json is found or
    ``stop_at`` is reached. Returns the absolute path or None."""
    return _find_nearest_ancestor(start_dir, stop_at, "package.json")


def find_nearest_pyproject_toml(
    start_dir: str | os.PathLike[str],
    stop_at: str | os.PathLike[str],
) -> str | None:
    """Walk up from ``start_dir`` until a pyproject.toml is found or
    ``stop_at`` is reached. Returns the absolute path or None."""
    return _find_nearest_ancestor(start_dir, stop_at, "pyproject.toml")


def find_nearest_makefile(
    start_dir: str | os.PathLike[str],
    stop_at: str | os.PathLike[str],
) -> str | None:
    """Walk up from ``start_dir`` until a Makefile (case-insensitive) is
    found or ``stop_at`` is reached. Returns the absolute path or None."""
    cur = os.path.abspath(str(start_dir))
    stop = os.path.abspath(str(stop_at))
    while True:
        for candidate in ("Makefile", "makefile", "GNUmakefile"):
            full = os.path.join(cur, candidate)
            if os.path.isfile(full):
                return full
        if cur == stop or len(cur) <= len(stop):
            return None
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _find_nearest_ancestor(
    start_dir: str | os.PathLike[str],
    stop_at: str | os.PathLike[str],
    filename: str,
) -> str | None:
    cur = os.path.abspath(str(start_dir))
    stop = os.path.abspath(str(stop_at))
    while True:
        candidate = os.path.join(cur, filename)
        if os.path.isfile(candidate):
            return candidate
        if cur == stop or len(cur) <= len(stop):
            return None
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def read_package_scripts(package_json_path: str | os.PathLike[str]) -> dict[str, str]:
    """Return the ``scripts`` object from a package.json, or ``{}``.

    Malformed files are treated as having no scripts so callers never crash
    on third-party packages with unusual formatting.
    """
    try:
        with open(package_json_path, "r", encoding="utf-8") as f:
            pkg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = pkg.get("scripts", {})
    return scripts if isinstance(scripts, dict) else {}


# ---------------------------------------------------------------------------
# FR table parser (from .shipwright/planning/*/spec.md)
# ---------------------------------------------------------------------------

def _fr_table_reader():
    # Same file-location load as _discovery(), and for the same reason: this
    # module is itself location-loaded by audit/audit_adapters, where no ``lib``
    # package is bound (ADR-045). fr_table_reader resolves ITS own siblings per
    # load style, so it is safe under all three.
    name = "_shipwright_fr_table_reader"
    if (mod := sys.modules.get(name)) is None:
        import importlib.util as _u
        spec = _u.spec_from_file_location(name, Path(__file__).with_name("fr_table_reader.py"))
        sys.modules[name] = mod = _u.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


@dataclass(frozen=True)
class FunctionalRequirement:
    id: str          # e.g. "FR-02.01"
    text: str
    priority: str    # "Must" | "Should" | "May"
    split: str       # split directory name, e.g. "02-dashboard"
    spec_path: str   # POSIX-style relative path, e.g. ".shipwright/planning/02-dashboard/spec.md"


def parse_fr_table(content: str, split: str, spec_path: str) -> list[FunctionalRequirement]:
    """Parse a spec.md body and return all *live* FR rows.

    A projection of ``fr_table_reader.read_active_fr_rows`` — this function owns
    the ``FunctionalRequirement`` shape and nothing else. It used to carry its
    own regex plus a removed-section loop that was a semantic clone of the RTM
    collector's, kept in sync by comment only; campaign step S4 removed both.

    Rows inside a ``## Removed Requirements`` / ``### Removed Requirements``
    section are skipped: a REMOVE-classified iterate moves retired FRs there and
    they must not count as live requirements.
    """
    return [
        FunctionalRequirement(
            id=row.id,
            text=row.text,
            priority=row.priority,
            split=split,
            spec_path=spec_path,
        )
        for row in _fr_table_reader().read_active_fr_rows(content)
    ]


# Canonical home of the planning artifact set, relative to project_root.
# Mirrors PLANNING_DIR in shared/scripts/lib/artifact_migrations.py — kept
# local here so callers don't need to import the manifest at runtime.
PLANNING_DIRNAME = ".shipwright/planning"


def collect_requirements_from_planning(
    project_root: str | os.PathLike[str],
) -> list[FunctionalRequirement]:
    """Walk ``<project_root>/.shipwright/planning/<split>/spec.md`` and collect FRs.

    Mirrors ``plugins/shipwright-compliance/.../data_collector.collect_requirements``
    so iterate 12.2 plan_checks can verify FR coherence without importing
    across plugin boundaries. Read-only; never writes.
    """
    root = Path(project_root)
    planning_dir = root / PLANNING_DIRNAME

    out: list[FunctionalRequirement] = []
    # guard="exists" keeps the historical behaviour that a planning FILE raises
    # NotADirectoryError rather than degrading to []. Frozen, not endorsed.
    for spec_path in _discovery().iter_spec_files(planning_dir, guard="exists"):
        split_name = spec_path.parent.name
        rel_spec = f"{PLANNING_DIRNAME}/{split_name}/spec.md"
        try:
            content = spec_path.read_text(encoding="utf-8")
        except OSError:
            continue
        out.extend(parse_fr_table(content, split_name, rel_spec))
    return out
