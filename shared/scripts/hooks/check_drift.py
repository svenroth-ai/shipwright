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
import sys
from pathlib import Path

# Hook bootstrap: hook execution context may have an unpredictable sys.path.
# Add the parent `shared/scripts` directory so `lib.drift_parsers` always
# resolves even when the hook is invoked with a minimal environment.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.drift_parsers import (  # noqa: E402  — after path bootstrap
    HIDDEN_DIR_DEFAULTS,
    build_paths_from_entries,
    extract_dev_blocks,
    extract_structure_block,
    find_nearest_package_json,
    load_gitignore,
    parse_npm_run_refs,
    parse_structure_entries,
    read_package_scripts,
)


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


def check_structure_drift(claude_md_path: str) -> list[str]:
    """Parse the Structure block and report filesystem mismatches."""
    try:
        with open(claude_md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []

    block = extract_structure_block(content)
    if block is None:
        return []

    entries = parse_structure_entries(block)
    if not entries:
        return []

    claude_dir = os.path.dirname(os.path.abspath(claude_md_path)) or "."
    paths = build_paths_from_entries(entries)

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

    gitignored = load_gitignore(resolve_base)

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
            real - documented - HIDDEN_DIR_DEFAULTS - gitignored
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

    blocks = extract_dev_blocks(content)
    if not blocks:
        return []

    claude_dir = os.path.dirname(os.path.abspath(claude_md_path))
    findings: list[str] = []
    seen: set[tuple[str, str]] = set()

    for block in blocks:
        for ref in parse_npm_run_refs(block):
            if ref.cd_target:
                pkg_dir = os.path.normpath(os.path.join(repo_root, ref.cd_target))
                pkg_path: str | None = os.path.join(pkg_dir, "package.json")
            else:
                pkg_path = find_nearest_package_json(claude_dir, repo_root)
                pkg_dir = os.path.dirname(pkg_path) if pkg_path else claude_dir

            key = (pkg_path or "", ref.script)
            if key in seen:
                continue
            seen.add(key)

            if not pkg_path or not os.path.isfile(pkg_path):
                rel_dir = os.path.relpath(pkg_dir, repo_root).replace(os.sep, "/")
                findings.append(
                    f"{claude_md_path}: references 'npm run {ref.script}' but no package.json at {rel_dir}/"
                )
                continue

            scripts = read_package_scripts(pkg_path)
            if ref.script not in scripts:
                rel_pkg = os.path.relpath(pkg_path, repo_root).replace(os.sep, "/")
                findings.append(
                    f"{claude_md_path}: references 'npm run {ref.script}' but not defined in {rel_pkg}"
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


# ---------------------------------------------------------------------------
# AC-5 of iterate-2026-05-14-triage-producers-2: triage emission
# ---------------------------------------------------------------------------


def _emit_drift_to_triage(
    project_root,
    timestamp_drifted: list[str],
    content_findings: list[str],
) -> int:
    """Append drift findings to ``.shipwright/triage.jsonl``.

    One triage item per finding. ``source="drift"``, ``severity="medium"``,
    ``kind="maintenance"``. Dedup key shape: ``f"drift:{file}:{kind}"`` with
    ``kind ∈ {"timestamp", "content"}``. ``match_commit=False`` +
    ``window_seconds=None`` means a given drift finding stays as ONE item
    indefinitely until it resolves or the operator dismisses it (same
    cross-session shape as the compliance producer).

    Best-effort: per-item errors logged to stderr and swallowed. The
    SessionStart hook MUST always exit 0 (informational), so emission
    failure can never block.
    """
    if not timestamp_drifted and not content_findings:
        return 0

    try:
        scripts_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), os.pardir,
        )
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from triage import append_triage_item_idempotent  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[drift] triage import failed: {type(exc).__name__}: {exc}\n"
        )
        return 0

    appended = 0
    for fname in timestamp_drifted:
        try:
            title = f"Drift: {fname} mtime newer than CLAUDE.md"[:160]
            detail = (
                f"Timestamp drift: {fname} was modified more recently than "
                f"CLAUDE.md. Re-read CLAUDE.md or refresh it before making "
                f"architectural decisions."
            )
            new_id = append_triage_item_idempotent(
                project_root,
                source="drift",
                severity="medium",
                kind="maintenance",
                title=title,
                detail=detail,
                dedup_key=f"drift:{fname}:timestamp",
                match_commit=False,
                window_seconds=None,
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[drift] timestamp triage emit failed for {fname}: "
                f"{type(exc).__name__}: {exc}\n"
            )

    for finding in content_findings:
        try:
            # Best-effort path extraction: every content finding starts with
            # `<path>: <human description>` per check_structure_drift /
            # check_command_drift. The path before the first ': ' is the
            # stable anchor.
            anchor = finding.split(": ", 1)[0].strip() or "CLAUDE.md"
            title = f"Drift: {finding[:120]}"[:160]
            new_id = append_triage_item_idempotent(
                project_root,
                source="drift",
                severity="medium",
                kind="maintenance",
                title=title,
                detail=finding,
                dedup_key=f"drift:{anchor}:content",
                match_commit=False,
                window_seconds=None,
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[drift] content triage emit failed: "
                f"{type(exc).__name__}: {exc}\n"
            )

    return appended


def main() -> int:
    try:
        scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
        sys.path.insert(0, scripts_dir)
        from lib.project_root import resolve_project_root
        project_root = str(resolve_project_root())
    except (ImportError, ValueError):
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

    # Iterate-2 AC-5: mirror drift findings into .shipwright/triage.jsonl.
    # Best-effort — must NOT change the hook's always-0 exit semantics.
    try:
        _emit_drift_to_triage(project_root, timestamp_drifted, content_findings)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[drift] triage emission top-level failed: "
            f"{type(exc).__name__}: {exc}\n"
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
