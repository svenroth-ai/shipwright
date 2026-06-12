#!/usr/bin/env python3
"""Artifact sync check — read-only drift detection.

Compares current code state against spec FRs using shipwright_sync_config.json mappings.
Output: JSON report of detected drift.
"""

import json
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# AC-5 of iterate-2026-05-14-triage-producers-2: triage emission
# ---------------------------------------------------------------------------


def _emit_drift_to_triage(project_root, affected: list[dict]) -> int:
    """Append artifact-drift findings to ``.shipwright/triage.jsonl``.

    One triage item per affected mapping (an entry from ``detect_drift()``'s
    ``affected`` list — a sync_config pattern whose changed_files intersect
    with `git diff`). ``source="drift"``, severity="medium",
    kind="maintenance", ``dedup_key=f"drift:{pattern}:artifact"``.
    ``match_commit=False`` + ``window_seconds=None`` mirrors the
    check_drift.py producer (same semantics, different detection site).

    Best-effort: per-item errors logged to stderr, swallowed. Returns the
    number of NEW items appended.
    """
    if not affected:
        return 0

    try:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from triage import append_triage_item_idempotent  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[drift] artifact_sync triage import failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return 0

    appended = 0
    for mapping in affected:
        try:
            pattern = str(mapping.get("pattern") or "unknown")
            changed = mapping.get("changed_files") or []
            artifacts = mapping.get("artifacts") or []
            frs = mapping.get("frs") or []
            title = f"Drift: code in {pattern} changed without artifact update"[:160]
            detail = (
                f"changed_files: {', '.join(str(c) for c in changed)} | "
                f"affected_artifacts: {', '.join(str(a) for a in artifacts) or 'n/a'} | "
                f"affected_FRs: {', '.join(str(f) for f in frs) or 'n/a'}"
            )
            new_id = append_triage_item_idempotent(
                project_root,
                source="drift",
                severity="medium",
                kind="maintenance",
                title=title,
                detail=detail,
                # CONTRACT: the `:artifact` suffix is load-bearing. This
                # producer shares source="drift" with
                # `check_drift.py::_emit_drift_to_triage`, whose resolve
                # pass scopes itself to `:timestamp`/`:content` keys so it
                # never retracts THIS producer's items. Changing this
                # suffix would silently break that cross-producer contract.
                dedup_key=f"drift:{pattern}:artifact",
                match_commit=False,
                window_seconds=None,
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[drift] artifact triage emit failed: "
                f"{type(exc).__name__}: {exc}\n"
            )
    return appended


def detect_drift(project_root: str, ref: str = "HEAD~1..HEAD") -> dict:
    """Detect artifact drift by comparing git diff against sync config."""
    root = Path(project_root)

    # Load sync config
    config_path = root / "shipwright_sync_config.json"
    if not config_path.exists():
        return {
            "drift_detected": False,
            "message": "No shipwright_sync_config.json found — cannot check drift",
            "affected": [],
        }

    # WP8/F24: explicit UTF-8 (utf-8-sig tolerates an optional BOM from a
    # hand-edited config) — the canonical writer (lib/config.py) emits FR
    # titles / descriptions with ensure_ascii=False, so a missing encoding=
    # here crashes on the cp1252 Windows dev platform for any non-ASCII
    # (CJK / Cyrillic) FR title.
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    mappings = config.get("mappings", [])

    # Get changed files from git
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", ref],
            capture_output=True, text=True, cwd=str(root),
        )
        changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (subprocess.SubprocessError, FileNotFoundError):
        return {
            "drift_detected": False,
            "message": "Could not read git diff",
            "affected": [],
        }

    if not changed_files:
        return {"drift_detected": False, "message": "No changes detected", "affected": []}

    # Match changed files against mappings
    import fnmatch
    affected = []

    for mapping in mappings:
        pattern = mapping.get("pattern", "")
        matching_files = [f for f in changed_files if fnmatch.fnmatch(f, pattern)]
        if matching_files:
            affected.append({
                "pattern": pattern,
                "changed_files": matching_files,
                "artifacts": mapping.get("artifacts", []),
                "frs": mapping.get("frs", []),
                "category": mapping.get("category", "unknown"),
            })

    if affected:
        # Iterate-2 AC-5: mirror drift findings into .shipwright/triage.jsonl.
        # Best-effort — never changes the return shape or raises.
        try:
            _emit_drift_to_triage(root, affected)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[drift] artifact_sync top-level triage emission failed: "
                f"{type(exc).__name__}: {exc}\n"
            )

    return {
        "drift_detected": len(affected) > 0,
        "message": f"{len(affected)} mapping(s) affected" if affected else "No drift detected",
        "affected": affected,
        "changed_files_total": len(changed_files),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Artifact sync drift detection")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--mode", choices=["detect"], default="detect")
    parser.add_argument("--ref", default="HEAD~1..HEAD", help="Git ref range")
    args = parser.parse_args()

    result = detect_drift(args.project_root, args.ref)
    print(json.dumps(result, indent=2))
    sys.exit(0 if not result["drift_detected"] else 1)


if __name__ == "__main__":
    main()
