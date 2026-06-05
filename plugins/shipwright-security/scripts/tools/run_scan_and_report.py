#!/usr/bin/env python3
"""Local-interactive OSS scanner wrapper.

Runs the OSS backend, redacts findings, persists a human Markdown report
plus a machine-readable JSON sidecar to ``.shipwright/securityreports/``
(with second-granularity history retention), and best-effort updates
``.gitignore``.

For Aikido backend, this wrapper short-circuits with a pointer to
``aikido_client.py report`` — Aikido has its own report path, untouched
by this iterate.

Usage:
    uv run scripts/tools/run_scan_and_report.py \
        --project-root . \
        [--repo owner/name] \
        [--full-evidence]

Exit codes:
    0  scan completed (or non-OSS backend short-circuit)
    1  scan failed or full-evidence refused in CI
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — make sibling scripts/lib + scripts/tools importable
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent.parent
SHARED_ROOT = PLUGIN_ROOT.parent.parent / "shared"

sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))
sys.path.insert(0, str(SHARED_ROOT / "scripts"))

try:
    from scanner_backend import get_backend  # type: ignore
    import oss_backend  # noqa: F401
    try:
        import aikido_client  # noqa: F401
    except ImportError:
        pass
except ImportError as exc:  # pragma: no cover - import safety
    print(f"Failed to import scanner backend: {exc}", file=sys.stderr)
    raise

from redact import redact_findings  # noqa: E402

import generate_security_report as gsr  # noqa: E402

try:
    from lib.errors import structured_success  # type: ignore
except (ImportError, ModuleNotFoundError):
    def structured_success(data=None):
        result = {"success": True}
        if data:
            result.update(data)
        return result


def _fix_windows_encoding() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORTS_DIR = ".shipwright/securityreports"  # relative to project_root
LEGACY_REPORTS_DIRNAME = "securityreports"   # pre-iterate-3 location, only used for upgrade notice
HISTORY_DIRNAME = "history"
LATEST_MD = "latest.md"
LATEST_JSON = "latest.json"
GITIGNORE_ENTRY = "/.shipwright/"            # ignore the whole hidden dir, future-proof
LEGACY_GITIGNORE_ENTRIES = {"/securityreports/", "securityreports/"}  # accepted as "present" during migration
RETAIN_PAIRS = 20

# Strict filename pattern for archived scans. User-added or malformed files
# in history/ that don't match are NEVER pruned — they stay where the user
# put them.
SCAN_FILENAME_RE = re.compile(r"^scan-(\d{8}-\d{6}-[0-9a-f]{6})\.(md|json)$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_scan_id(now: datetime) -> str:
    """``scan-YYYYMMDD-HHMMSS-{6 hex}`` — second-grain + uuid for collision-safety."""
    ts = now.strftime("%Y%m%d-%H%M%S")
    return f"scan-{ts}-{uuid.uuid4().hex[:6]}"


def _atomic_write(path: Path, text: str) -> None:
    """Write text to ``path`` atomically: tmp file in same dir + os.replace.

    Same-directory tmp avoids cross-drive rename failures on Windows. The
    tmp file is opened with delete=False so the os.replace can succeed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".tmp", prefix=path.name + ".", dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _ensure_gitignore_entry(project_root: Path) -> str:
    """Best-effort gitignore append.

    - If .gitignore is missing → skip silently (don't materialize one).
    - If .gitignore exists and contains the entry → no-op (idempotent).
    - Else → append, ensuring the existing file ends with a newline first.

    Returns: 'added' | 'present' | 'skipped'
    """
    gi = project_root / ".gitignore"
    if not gi.exists():
        return "skipped"

    existing = gi.read_text(encoding="utf-8")
    # Match exact entry on its own line. Accept the new `/.shipwright/`
    # canonical form AND the legacy `/securityreports/` (kept idempotent
    # for projects mid-migration so we don't double-write).
    accepted = {GITIGNORE_ENTRY} | LEGACY_GITIGNORE_ENTRIES
    lines = existing.splitlines()
    for line in lines:
        if line.strip() in accepted:
            return "present"

    # Need to append. Ensure file ends with a newline before adding our entry,
    # otherwise we'd merge with the last existing line.
    suffix = "" if existing.endswith("\n") else "\n"
    addition = f"{suffix}{GITIGNORE_ENTRY}\n"
    gi.write_text(existing + addition, encoding="utf-8")
    return "added"


def _list_archived_scans(history_dir: Path) -> list[tuple[str, list[Path]]]:
    """Return list of (scan_id_stem, [files]) ordered newest-first.

    Only files matching SCAN_FILENAME_RE are considered — manual / malformed
    files in the directory are ignored.
    """
    if not history_dir.exists():
        return []

    by_stem: dict[str, list[Path]] = {}
    for child in history_dir.iterdir():
        if not child.is_file():
            continue
        m = SCAN_FILENAME_RE.match(child.name)
        if not m:
            continue
        stem = f"scan-{m.group(1)}"
        by_stem.setdefault(stem, []).append(child)

    # Newest stem first (lexicographic sort works because YYYYMMDD-HHMMSS stems
    # are monotonic).
    return sorted(by_stem.items(), key=lambda kv: kv[0], reverse=True)


def _emit_legacy_dir_notice(project_root: Path) -> bool:
    """Print a one-time stderr notice if the project has a stale legacy
    ``securityreports/`` directory but no new ``.shipwright/securityreports/``.

    Best-effort, never raises, never blocks the scan. Returns True if the
    notice was emitted (used by tests).
    """
    legacy = project_root / LEGACY_REPORTS_DIRNAME
    new = project_root / REPORTS_DIR
    if legacy.is_dir() and not new.exists():
        print(
            f"[shipwright-security] notice: report directory moved to "
            f"`{REPORTS_DIR}/`. Old folder at `{LEGACY_REPORTS_DIRNAME}/` is "
            f"stale and safe to delete (or `git mv {LEGACY_REPORTS_DIRNAME} "
            f".shipwright/`).",
            file=sys.stderr,
        )
        return True
    return False


def _prune_history(history_dir: Path, retain: int = RETAIN_PAIRS) -> int:
    """Delete archived scans beyond the retain limit; return count removed."""
    grouped = _list_archived_scans(history_dir)
    to_delete = grouped[retain:]
    removed = 0
    for _stem, files in to_delete:
        for f in files:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    return removed


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def _build_md_with_scan_id(
    findings: list[dict[str, Any]], repo: str, scan_id: str,
    scan_errors: list[dict[str, Any]] | None = None,
) -> str:
    """Build the human-readable Markdown report with an HTML-comment scan_id header."""
    body = gsr.generate_standard_report(findings, repo, scan_errors)
    # Embed scan_id as the first line so latest.md ↔ latest.json correlate
    return f"<!-- scan_id: {scan_id} -->\n{body}"


def _build_json_with_scan_id(
    findings: list[dict[str, Any]], repo: str, scan_id: str,
    scan_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = gsr.build_json_sidecar(findings, repo, scan_errors)
    payload["scan_id"] = scan_id
    return payload


def run(*, project_root: Path, repo: str = "unknown", full_evidence: bool = False) -> int:
    """Programmatic entry point — return exit code (0 success, 1 failure)."""
    # Refuse --full-evidence in CI to avoid persisting raw secrets in shared
    # disk artifacts. Tests document this contract.
    if full_evidence and os.environ.get("CI"):
        print(
            "[shipwright-security] refusing --full-evidence in CI environment. "
            "Re-run locally or unset CI=.",
            file=sys.stderr,
        )
        return 1

    backend = get_backend()
    if getattr(backend, "name", None) != "oss":
        print(
            "[shipwright-security] non-OSS backend detected — this wrapper is "
            "OSS-only. For Aikido, run: "
            "uv run plugins/shipwright-security/scripts/lib/aikido_client.py report",
            file=sys.stderr,
        )
        return 0

    # One-time stderr notice if a legacy securityreports/ directory exists.
    # Emitted before the scan so users see it even if the scan errors.
    _emit_legacy_dir_notice(project_root)

    target = str(project_root)
    raw_findings = backend.scan(target)
    # Degraded-leg markers (empty for backends/mocks that never set the attr;
    # the isinstance guard rejects a MagicMock auto-attribute).
    raw_errors = getattr(backend, "scan_errors", [])
    scan_errors = list(raw_errors) if isinstance(raw_errors, list) else []

    # Default-on redaction unless explicitly opted out
    findings = redact_findings(raw_findings, full_evidence=full_evidence)

    now = datetime.now(timezone.utc)
    scan_id = _new_scan_id(now)

    md_text = _build_md_with_scan_id(findings, repo, scan_id, scan_errors)
    json_payload = _build_json_with_scan_id(findings, repo, scan_id, scan_errors)
    json_text = json.dumps(json_payload, ensure_ascii=False, indent=2) + "\n"

    reports_dir = project_root / REPORTS_DIR
    history_dir = reports_dir / HISTORY_DIRNAME
    history_dir.mkdir(parents=True, exist_ok=True)

    # Atomic write of the latest.* pair
    _atomic_write(reports_dir / LATEST_MD, md_text)
    _atomic_write(reports_dir / LATEST_JSON, json_text)

    # Archive (separate atomic writes — by design they share the same scan_id
    # so a partial-write crash is detectable from latest.md ↔ latest.json mismatch).
    _atomic_write(history_dir / f"{scan_id}.md", md_text)
    _atomic_write(history_dir / f"{scan_id}.json", json_text)

    removed = _prune_history(history_dir)

    gitignore_status = _ensure_gitignore_entry(project_root)

    summary = structured_success(data={
        "command": "run_scan_and_report",
        "scan_id": scan_id,
        "findings_count": len(findings),
        "degraded": bool(scan_errors),
        "scan_errors": scan_errors,
        "report_md": str(reports_dir / LATEST_MD),
        "report_json": str(reports_dir / LATEST_JSON),
        "history_pruned": removed,
        "gitignore": gitignore_status,
        "redaction": "off" if full_evidence else "on",
    })
    print(json.dumps(summary, ensure_ascii=False))
    # A degraded scan is not a clean success — report it (exit 1) so a local
    # caller / wrapper sees the same fail-closed signal the CI gate enforces.
    return 1 if scan_errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root (default: cwd)")
    parser.add_argument("--repo", default="unknown", help="Repository name for the report header")
    parser.add_argument(
        "--full-evidence",
        action="store_true",
        help="Retain raw secret evidence in findings. Refused when CI env is set. "
             "Use only for explicit local debugging.",
    )
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    return run(project_root=project_root, repo=args.repo, full_evidence=args.full_evidence)


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())
