"""Drift detector for relocated Shipwright artifact directories.

Scans the project root for any *legacy* top-level directory whose
canonical home is now under ``.shipwright/`` (per
``ARTIFACT_MIGRATIONS``). When the corresponding migration is

- ``in_progress`` → emit warn-only stderr notice + write report to
  ``.shipwright/stale-folders.md``. Hook continues with exit 0.
- ``migrated``    → emit structured JSON to stdout (parsable by the
  AI orchestrator) and exit 1. Hook hard-gates the session.

Self-healing: when no findings exist on a subsequent run, the report
file is *deleted* (``unlink(missing_ok=True)``) instead of overwritten,
so the absence of the file is the canonical "no drift" signal.

See ``docs/migrations/artifact-migration-reference.md`` (Sub-Iterate G
deliverable) for the full pattern and rationale.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from artifact_migrations import active_migrations  # type: ignore
except ImportError:  # pragma: no cover — script-mode fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from artifact_migrations import active_migrations  # type: ignore


REPORT_FILENAME = ".shipwright/stale-folders.md"
SAMPLE_CAP = 50  # streaming presence check stops after N files

# Markdown-special characters that need escaping when rendering paths
# into the report (defense-in-depth against unusual filenames).
_MD_ESCAPE_RE = re.compile(r"([\\`*_{}\[\]()#+!|])")


def _escape_md(text: str) -> str:
    """Escape Markdown-special characters in a path-derived string."""
    return _MD_ESCAPE_RE.sub(r"\\\1", text)


def scan_for_stale_legacy_dirs(project_root: Path) -> list[dict[str, Any]]:
    """Walk *project_root* for legacy artifact dirs of active migrations.

    Streaming presence check — never materializes the full file list,
    stops after ``SAMPLE_CAP`` files per legacy directory. Fails open on
    ``OSError`` (broken symlink, permission denied) by reporting the
    directory as drifted rather than crashing.

    Returns a list of finding dicts with keys: ``name``, ``status``,
    ``legacy_path``, ``canonical_path``, ``canonical_exists``,
    ``sample_count`` (≤SAMPLE_CAP, equal value indicates capped),
    ``severity`` (``"block"`` for migrated, ``"warn"`` for in_progress).
    """
    findings: list[dict[str, Any]] = []
    for migration in active_migrations():
        legacy = project_root / migration["legacy_dirname"]
        if not legacy.is_dir():
            continue

        has_files = False
        sample_count = 0
        try:
            for entry in legacy.rglob("*"):
                if entry.is_file():
                    has_files = True
                    sample_count += 1
                    if sample_count >= SAMPLE_CAP:
                        break
        except OSError:
            has_files = True  # err on side of reporting

        if not has_files:
            continue

        canonical = project_root / migration["canonical"]
        findings.append({
            "name": migration["name"],
            "status": migration["status"],
            "legacy_path": str(legacy),
            "canonical_path": str(canonical),
            "canonical_exists": canonical.exists(),
            "sample_count": sample_count,
            "severity": "block" if migration["status"] == "migrated" else "warn",
        })
    return findings


def _render_drift_md(findings: list[dict[str, Any]], ts: datetime) -> str:
    """Render the report markdown. Escapes path strings."""
    lines = [
        "# Shipwright drift report",
        "",
        f"_Generated: {ts.isoformat()}_",
        "",
        "Legacy artifact directories were detected at the project root.",
        "These should live under `.shipwright/` per the relocation convention.",
        "",
    ]
    for f in findings:
        legacy = _escape_md(f["legacy_path"])
        canonical = _escape_md(f["canonical_path"])
        sample = f["sample_count"]
        sample_str = f"{sample}+" if sample >= SAMPLE_CAP else str(sample)
        canon_state = "exists" if f["canonical_exists"] else "MISSING"

        lines.extend([
            f"## `{f['name']}` ({f['severity']})",
            "",
            f"- **Legacy path**: `{legacy}` ({sample_str} file(s) detected)",
            f"- **Canonical path**: `{canonical}` ({canon_state})",
            f"- **Migration status**: `{f['status']}`",
            "",
            "**Remediation:**",
            "",
            "```bash",
            f"git mv {f['legacy_path']} {f['canonical_path']}",
            "```",
            "",
        ])
    return "\n".join(lines)


def write_drift_report_or_clear(
    project_root: Path,
    findings: list[dict[str, Any]],
) -> Path | None:
    """Write the report when findings exist, delete it otherwise.

    Self-healing: ``unlink(missing_ok=True)`` keeps the file's presence
    as the canonical drift signal (no stale timestamps, no diff churn).

    Returns the report path when written, else ``None``.
    """
    out = project_root / REPORT_FILENAME
    if not findings:
        out.unlink(missing_ok=True)
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    body = _render_drift_md(findings, ts=datetime.now(timezone.utc))
    out.write_text(body, encoding="utf-8")
    return out


def hook_main(project_root: Path) -> int:
    """SessionStart-hook entry point.

    - Wraps scan in try/except so a broken filesystem cannot brick the
      session start.
    - On ``block``-severity findings (migrated artifacts with stale
      legacy dirs), prints structured JSON to stdout and exits 1 so the
      AI orchestrator reliably notices.
    - On ``warn`` findings (in-progress migrations), only stderr-notes
      and exits 0 — we do not want to block our own migration sub-iterates.
    """
    try:
        findings = scan_for_stale_legacy_dirs(project_root)
    except Exception as exc:  # pragma: no cover — defensive fail-open
        print(f"[shipwright] drift detector skipped: {exc}", file=sys.stderr)
        return 0

    write_drift_report_or_clear(project_root, findings)

    blocking = [f for f in findings if f["severity"] == "block"]
    if blocking:
        print(json.dumps({
            "success": False,
            "error": "stale_artifact_dirs",
            "findings": blocking,
            "remediation": [
                f"git mv {f['legacy_path']} {f['canonical_path']}"
                for f in blocking
            ],
        }))
        return 1

    if findings:
        print(
            f"[shipwright] drift warning: {len(findings)} legacy dir(s) "
            f"seen during in-progress migration; see "
            f"`{REPORT_FILENAME}`",
            file=sys.stderr,
        )
    return 0
