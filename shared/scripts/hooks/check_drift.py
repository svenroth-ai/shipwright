#!/usr/bin/env python3
"""SessionStart hook: Detect CLAUDE.md drift from source code changes.

**Content drift** -- parses the Structure block and Development block of
every CLAUDE.md at `./CLAUDE.md` and `*/CLAUDE.md` (one level down) and
compares them to the actual filesystem and to `package.json` scripts.
Catches missing plugin folders, obsolete directory listings, and
`npm run <script>` references to scripts that no longer exist.

A former *timestamp drift* detector (compared `CLAUDE.md`'s mtime against a
hard-coded config-file list) was removed in iterate-2026-06-28: filesystem
mtime is not a content-staleness signal in a git repo -- a checkout, branch
switch, worktree creation, or a release `version =` bump resets mtimes, so it
fired on noise (e.g. every worktree-based iterate). Content drift is the
deterministic, content-based replacement. The triage resolve pass below still
dismisses any pre-existing ``:timestamp`` drift items left over from that era.

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

# F7 (project guard) + F8 (repo-relative dedup anchor) live in lib.drift_anchor
# so they can be unit-tested and reused independently. Re-exported under their
# historical ``_``-private names here.
from lib.drift_anchor import (  # noqa: E402, F401  (re-exported under historical names)
    canonical_anchor as _canonical_anchor,
    content_anchor as _content_anchor,
    is_shipwright_project as _is_shipwright_project,
)


def _emit_drift_to_triage(
    project_root,
    content_findings: list[str],
) -> int:
    """Append content-drift findings to the triage store and resolve stale ones.

    One triage item per finding. ``source="drift"``, ``severity="medium"``,
    ``kind="maintenance"``, dedup key ``f"drift:{anchor}:content"``.
    ``match_commit=False`` + ``window_seconds=None`` → a drift finding stays as
    ONE item until it resolves / is dismissed. The ``content`` path is
    canonicalized **repo-relative** via :func:`_canonical_anchor` so neither
    drive-letter casing (Bug 1) nor an absolute tree prefix (F8) can split one
    logical drift.

    **F7 project guard:** no-ops (returns 0, writes nothing) unless
    ``project_root`` is a Shipwright-managed project — without it, opening a
    foreign repo with a stale ``CLAUDE.md`` wrote ``.shipwright/triage.jsonl``
    into a tree the framework isn't installed in.

    **Resolve pass (Bug 2):** after appending, every still-open
    (``status == "triage"``) ``source="drift"`` item THIS detector owns (key
    ending ``:content`` — or a legacy ``:timestamp`` item from the removed
    timestamp detector — but NOT ``artifact_sync``'s ``:artifact``) whose key is
    absent from the current set flips to ``dismissed``. The ``:timestamp`` branch
    is retained purely to retire any stale items left by the old detector; this
    producer never emits a new ``:timestamp`` item.

    Best-effort: per-item errors logged + swallowed (the SessionStart hook MUST
    exit 0). Returns the count of NEW items appended.
    """
    if not _is_shipwright_project(project_root):
        # F7: never write triage state into a non-Shipwright tree.
        return 0
    try:
        scripts_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), os.pardir,
        )
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from triage import (  # noqa: PLC0415
            append_triage_item_idempotent,
            mark_status,
            read_all_items,
            should_route_to_outbox,
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[drift] triage import failed: {type(exc).__name__}: {exc}\n"
        )
        return 0

    # D1 review cascade: SessionStart is a genuine idle-main background
    # appender — route its appends to the outbox on idle main WITH origin
    # (else tracked). The resolve-pass mark_status is residence-derived.
    to_outbox = should_route_to_outbox(project_root)

    # The full set of dedup keys this run produced — drives BOTH the
    # idempotent append and the resolve pass below. Only ``:content`` keys are
    # produced now; any open ``:timestamp`` item is therefore absent from this
    # set and gets dismissed by the resolve pass (legacy cleanup).
    current_keys = {
        f"drift:{_content_anchor(f, project_root)}:content" for f in content_findings
    }

    appended = 0
    for finding in content_findings:
        try:
            # The title/detail keep the original-case path for the human
            # reader; only the dedup key is canonicalized (Bug 1 fix —
            # drive-letter casing must not split one drift across two items).
            title = f"Drift: {finding[:120]}"[:160]
            new_id = append_triage_item_idempotent(
                project_root,
                source="drift",
                severity="medium",
                kind="maintenance",
                title=title,
                detail=finding,
                dedup_key=f"drift:{_content_anchor(finding, project_root)}:content",
                match_commit=False,
                window_seconds=None,
                to_outbox=to_outbox,
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[drift] content triage emit failed: "
                f"{type(exc).__name__}: {exc}\n"
            )

    # Resolve pass (Bug 2 fix) — dismiss this detector's own stale items
    # whose drift condition has cleared (key no longer in current_keys).
    try:
        for item in read_all_items(project_root):
            if item.get("source") != "drift":
                continue
            if item.get("status") != "triage":
                continue
            dk = item.get("dedupKey") or ""
            # Only keys THIS detector owns — artifact_sync.py shares
            # source="drift" with `:artifact` keys that must not be touched.
            if not (dk.endswith(":timestamp") or dk.endswith(":content")):
                continue
            if dk in current_keys:
                continue
            try:
                mark_status(
                    project_root,
                    item["id"],
                    new_status="dismissed",
                    by="driftDetector",
                    reason="driftResolved",
                )
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(
                    f"[drift] resolve mark_status failed for "
                    f"{item.get('id')}: {type(exc).__name__}: {exc}\n"
                )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[drift] resolve pass failed: {type(exc).__name__}: {exc}\n"
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

    # Content drift -- structure + commands. (The former timestamp-drift
    # detector was removed in iterate-2026-06-28: mtime is not a content
    # signal in a git repo — see the module docstring.)
    content_findings: list[str] = []
    for claude_md in _find_claude_md_files(project_root):
        content_findings.extend(check_structure_drift(claude_md))
        content_findings.extend(check_command_drift(claude_md, project_root))

    if content_findings:
        warnings.append(
            "Content drift in CLAUDE.md:\n  - " + "\n  - ".join(content_findings)
        )

    # Iterate-2 AC-5: mirror drift findings into .shipwright/triage.jsonl.
    # Best-effort — must NOT change the hook's always-0 exit semantics. Also
    # retires any stale ``:timestamp`` items left by the removed detector.
    try:
        _emit_drift_to_triage(project_root, content_findings)
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
