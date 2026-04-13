#!/usr/bin/env python3
"""SessionStart hook: Detect CLAUDE.md drift from source code changes.

Two kinds of drift are surfaced:

1. **Timestamp drift** (original) -- if hard-coded config/source files have
   been modified more recently than CLAUDE.md, the agent should refresh
   its mental model before making architectural decisions.

2. **Content drift** -- parses the Structure block and Development block of
   every CLAUDE.md at `./CLAUDE.md` and `*/CLAUDE.md` (one level down) and
   compares them to the actual filesystem and to `package.json` scripts.
   Catches missing plugin folders, obsolete directory listings, and
   `npm run <script>` references to scripts that no longer exist.

Exit codes:
  0 = allow (always -- informational warning only, never blocks)
"""

from __future__ import annotations

import json
import os
import re
import sys


# ---------------------------------------------------------------------------
# Timestamp drift (original behaviour, kept intact)
# ---------------------------------------------------------------------------

KEY_FILES = [
    "package.json",
    "pyproject.toml",
    "tsconfig.json",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "docker-compose.yml",
    "Dockerfile",
]

KEY_DIRS = ["src", "app", "lib", "packages"]


def get_mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def get_newest_in_dir(directory: str, max_depth: int = 2) -> float | None:
    newest = None
    try:
        for root, dirs, files in os.walk(directory):
            depth = root.replace(directory, "").count(os.sep)
            if depth >= max_depth:
                dirs.clear()
                continue
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d not in ("node_modules", "__pycache__", "vendor", "dist", "build")
            ]
            for f in files:
                if f.startswith("."):
                    continue
                fp = os.path.join(root, f)
                mt = get_mtime(fp)
                if mt and (newest is None or mt > newest):
                    newest = mt
    except OSError:
        pass
    return newest


def check_timestamp_drift(project_root: str) -> list[str]:
    claude_md = os.path.join(project_root, "CLAUDE.md")
    claude_mtime = get_mtime(claude_md)
    if claude_mtime is None:
        return []

    drifted: list[str] = []
    for fname in KEY_FILES:
        mt = get_mtime(os.path.join(project_root, fname))
        if mt and mt > claude_mtime:
            drifted.append(fname)

    for dirname in KEY_DIRS:
        dpath = os.path.join(project_root, dirname)
        if os.path.isdir(dpath):
            mt = get_newest_in_dir(dpath)
            if mt and mt > claude_mtime:
                drifted.append(f"{dirname}/ (source changes)")

    return drifted


# ---------------------------------------------------------------------------
# Content drift -- Structure block parsing
# ---------------------------------------------------------------------------

# Matches a Structure block line: optional indent, identifier (optionally
# with trailing slash for dirs), optional `# comment`.
_STRUCT_ENTRY_RE = re.compile(r"^(?P<indent>\s*)(?P<name>[\w.-]+)(?P<slash>/?)\s*(?:#.*)?$")

# Matches a fenced code block following "## Structure" or "### Structure".
_STRUCTURE_BLOCK_RE = re.compile(
    r"#{2,3}\s+Structure\s*\n+```[^\n]*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_structure_block(content: str) -> str | None:
    m = _STRUCTURE_BLOCK_RE.search(content)
    return m.group(1) if m else None


def _parse_structure_entries(block: str) -> list[tuple[int, str, bool]]:
    """Return (indent, name, is_dir) for each recognizable entry."""
    entries: list[tuple[int, str, bool]] = []
    for line in block.splitlines():
        if not line.strip():
            continue
        m = _STRUCT_ENTRY_RE.match(line)
        if not m:
            continue
        name = m.group("name")
        # Skip obvious non-entries (pure comments, backticks, etc.)
        if name.startswith("_") and name.endswith("_"):
            continue
        entries.append((len(m.group("indent")), name, bool(m.group("slash"))))
    return entries


def _build_paths_from_entries(
    entries: list[tuple[int, str, bool]],
) -> list[tuple[str, bool]]:
    """Resolve each entry into a POSIX-style path (using `/`).

    Uses indent levels to reconstruct the parent chain.
    Returns list of (relative_path, is_dir).
    """
    stack: list[tuple[int, str]] = []  # (indent, accumulated_path)
    out: list[tuple[str, bool]] = []
    for indent, name, is_dir in entries:
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1] if stack else ""
        path = f"{parent}/{name}" if parent else name
        stack.append((indent, path))
        out.append((path, is_dir))
    return out


def _load_gitignore(root: str) -> set[str]:
    """Return the set of top-level names ignored by .gitignore (rough heuristic).

    Only handles simple `name/` or `name` entries at the root level -- enough
    to filter the common drift noise (node_modules, dist, .venv, etc.).
    """
    ignored: set[str] = set()
    gi = os.path.join(root, ".gitignore")
    if not os.path.exists(gi):
        return ignored
    try:
        with open(gi, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                # strip leading slash and trailing slash
                line = line.lstrip("/").rstrip("/")
                # ignore patterns with wildcards beyond a plain name
                if any(ch in line for ch in "*?[]"):
                    continue
                ignored.add(line)
    except OSError:
        pass
    return ignored


_HIDDEN_DIR_DEFAULTS = {
    # Build/test artifacts
    "node_modules", "__pycache__", "dist", "build", ".venv", ".git",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".idea", ".vscode",
    "vendor", "e2e-results", "playwright-report", "test-results",
    # Shipwright runtime artifacts of target projects (every shipwright-built
    # project has these; they are state, not architecture, so they should not
    # surface as drift findings when CLAUDE.md doesn't enumerate them).
    "agent_docs", "designs", "planning", "compliance",
}


def check_structure_drift(claude_md_path: str) -> list[str]:
    """Parse the Structure block and report filesystem mismatches."""
    try:
        with open(claude_md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []

    block = _extract_structure_block(content)
    if block is None:
        return []

    entries = _parse_structure_entries(block)
    if not entries:
        return []

    claude_dir = os.path.dirname(os.path.abspath(claude_md_path)) or "."
    paths = _build_paths_from_entries(entries)

    # Wrapper-root detection: some CLAUDE.md files start the tree with their
    # own directory name (e.g. `webui/` in `webui/CLAUDE.md`). In that case
    # resolve everything against the parent directory so the tree lines up.
    top_level_entries = [name for indent, name, _ in entries if indent == 0]
    is_wrapper_root = (
        len(top_level_entries) == 1
        and top_level_entries[0] == os.path.basename(claude_dir)
    )
    resolve_base = os.path.dirname(claude_dir) if is_wrapper_root else claude_dir

    findings: list[str] = []

    for rel_path, is_dir in paths:
        # rel_path uses forward slashes; convert for os.path ops.
        full = os.path.normpath(os.path.join(resolve_base, rel_path))

        if is_dir:
            if not os.path.isdir(full):
                findings.append(
                    f"{claude_md_path}: Structure lists '{rel_path}/' but directory not found"
                )
        else:
            # File entry -- only flag if the parent dir exists but the file does not,
            # and only at shallow depth to avoid noise over renamed internals.
            if os.path.isdir(os.path.dirname(full)) and not os.path.exists(full):
                depth = rel_path.count("/")
                if depth <= 2:
                    findings.append(
                        f"{claude_md_path}: Structure lists '{rel_path}' but file not found"
                    )

    # Undocumented directories at every enumerated level.
    #
    # Build a map: documented_children[parent_rel_path] = set of child names.
    # A parent of "" means "top-level siblings of the CLAUDE.md location".
    # For any dir entry whose children ARE enumerated in the Structure tree,
    # compare against the real filesystem and flag extra dirs.
    documented_children: dict[str, set[str]] = {}
    for rel_path, _ in paths:
        if "/" in rel_path:
            parent, _, name = rel_path.rpartition("/")
        else:
            parent, name = "", rel_path
        documented_children.setdefault(parent, set()).add(name)

    gitignored = _load_gitignore(resolve_base)

    # (parent_rel_path, absolute_dir) pairs to check. Top level only for
    # non-wrapper roots; wrapper roots skip the "" level (siblings of webui/
    # shouldn't concern webui/CLAUDE.md).
    parents_to_scan: list[tuple[str, str]] = []
    if not is_wrapper_root and "" in documented_children:
        parents_to_scan.append(("", resolve_base))
    # Every documented directory entry that has documented children becomes
    # a parent whose listing we verify.
    for rel_path, is_dir in paths:
        if not is_dir:
            continue
        if rel_path not in documented_children:
            continue
        full = os.path.normpath(os.path.join(resolve_base, rel_path))
        if os.path.isdir(full):
            parents_to_scan.append((rel_path, full))

    for parent_rel, parent_abs in parents_to_scan:
        documented = documented_children.get(parent_rel, set())
        try:
            real = {
                name for name in os.listdir(parent_abs)
                if os.path.isdir(os.path.join(parent_abs, name))
                and not name.startswith(".")
            }
        except OSError:
            continue
        undocumented = (
            real - documented - _HIDDEN_DIR_DEFAULTS - gitignored
        )
        for name in sorted(undocumented):
            display = f"{parent_rel}/{name}" if parent_rel else name
            findings.append(
                f"{claude_md_path}: '{display}/' exists on disk but not listed in Structure"
            )

    return findings


# ---------------------------------------------------------------------------
# Content drift -- Development command parsing
# ---------------------------------------------------------------------------

_DEV_BLOCK_RE = re.compile(
    r"#{2,3}\s+Development\b.*?```bash\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)
# Matches: "npm run <script>" with optional "cd <dir> && " prefix.
_NPM_RUN_RE = re.compile(
    r"(?:cd\s+(?P<cd>[\w./-]+)\s*&&\s*)?npm\s+run\s+(?P<script>[\w:-]+)"
)


def _extract_dev_blocks(content: str) -> list[str]:
    return _DEV_BLOCK_RE.findall(content)


def _find_nearest_package_json(start_dir: str, stop_at: str) -> str | None:
    """Walk up from start_dir until a package.json is found or stop_at is reached."""
    cur = os.path.abspath(start_dir)
    stop = os.path.abspath(stop_at)
    while True:
        candidate = os.path.join(cur, "package.json")
        if os.path.isfile(candidate):
            return candidate
        if cur == stop or len(cur) <= len(stop):
            return None
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def check_command_drift(claude_md_path: str, repo_root: str) -> list[str]:
    """Verify every `npm run <script>` in Development blocks resolves to a real script.

    Convention: `cd <dir>` targets are resolved from the repo root (the CWD
    where the hook runs). This matches how dev instructions in CLAUDE.md
    files are normally written -- "run from the repo root".
    """
    try:
        with open(claude_md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []

    blocks = _extract_dev_blocks(content)
    if not blocks:
        return []

    claude_dir = os.path.dirname(os.path.abspath(claude_md_path))
    findings: list[str] = []
    seen: set[tuple[str, str]] = set()

    for block in blocks:
        for match in _NPM_RUN_RE.finditer(block):
            cd_target = match.group("cd")
            script = match.group("script")

            if cd_target:
                pkg_dir = os.path.normpath(os.path.join(repo_root, cd_target))
                pkg_path = os.path.join(pkg_dir, "package.json")
            else:
                pkg_path = _find_nearest_package_json(claude_dir, repo_root)
                pkg_dir = os.path.dirname(pkg_path) if pkg_path else claude_dir

            key = (pkg_path or "", script)
            if key in seen:
                continue
            seen.add(key)

            if not pkg_path or not os.path.isfile(pkg_path):
                rel_dir = os.path.relpath(pkg_dir, repo_root).replace(os.sep, "/")
                findings.append(
                    f"{claude_md_path}: references 'npm run {script}' but no package.json at {rel_dir}/"
                )
                continue

            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            scripts = pkg.get("scripts", {})
            if script not in scripts:
                rel_pkg = os.path.relpath(pkg_path, repo_root).replace(os.sep, "/")
                findings.append(
                    f"{claude_md_path}: references 'npm run {script}' but not defined in {rel_pkg}"
                )

    return findings


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _find_claude_md_files(root: str) -> list[str]:
    """Return ./CLAUDE.md and */CLAUDE.md one level down."""
    out: list[str] = []
    top = os.path.join(root, "CLAUDE.md")
    if os.path.isfile(top):
        out.append(top)
    try:
        for name in os.listdir(root):
            if name.startswith("."):
                continue
            sub = os.path.join(root, name)
            if os.path.isdir(sub):
                candidate = os.path.join(sub, "CLAUDE.md")
                if os.path.isfile(candidate):
                    out.append(candidate)
    except OSError:
        pass
    return out


def main() -> int:
    project_root = os.getcwd()
    warnings: list[str] = []

    # 1. Timestamp drift (legacy behaviour)
    timestamp_drifted = check_timestamp_drift(project_root)
    if timestamp_drifted:
        warnings.append(
            "Timestamp drift: CLAUDE.md may be outdated. These files changed more recently: "
            + ", ".join(timestamp_drifted)
        )

    # 2. Content drift -- structure + commands
    content_findings: list[str] = []
    for claude_md in _find_claude_md_files(project_root):
        content_findings.extend(check_structure_drift(claude_md))
        content_findings.extend(check_command_drift(claude_md, project_root))

    if content_findings:
        warnings.append(
            "Content drift in CLAUDE.md:\n  - " + "\n  - ".join(content_findings)
        )

    if warnings:
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "DRIFT WARNING: CLAUDE.md may be out of sync with the codebase. "
                    "Consider updating it before making architectural decisions.\n\n"
                    + "\n\n".join(warnings)
                ),
            }
        }
        print(json.dumps(payload))

    return 0  # Never block -- informational only


if __name__ == "__main__":
    sys.exit(main())
