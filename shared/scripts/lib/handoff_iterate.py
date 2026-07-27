"""In-flight ITERATE progress for the generated session handoff.

Moved verbatim out of ``tools/generate_session_handoff.py``: that module carries a
*grandfathered* bloat-baseline entry at exactly its own size, so its sibling
renderer (``handoff_pipeline.render_pipeline_phases``) could not be added there
without ratcheting it. Both are handoff progress sections; keeping each in its own
module keeps both well inside the size budget.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def render_iterate_progress(project_root: Path, git_info: dict) -> list[str]:
    """Return lines describing in-progress iterate state.

    Step B1 Resume in the iterate skill needs reliable evidence for which
    mandatory phases still need to run when a previous session was
    interrupted. The rest of the handoff is an overview of completed work
    (iterate_history, recent events). This block fills that gap for an ITERATE
    by inspecting the iterate branch + the run-scoped marker files directly —
    agents reading the handoff on Resume should trust this section over
    heuristics. (The equivalent gap for a PIPELINE run is filled by
    ``handoff_pipeline.render_pipeline_phases``.)

    Returns an empty list if not on an iterate branch.
    """
    branch = git_info.get("branch") or ""
    if not branch.startswith("iterate/"):
        return []

    iterate_dir = project_root / ".shipwright" / "planning" / "iterate"
    short = branch.removeprefix("iterate/").split("/")[-1].lower()

    spec_path: Path | None = None
    run_id: str = ""
    complexity: str = ""
    if iterate_dir.exists():
        candidates = [
            p for p in iterate_dir.glob("*.md")
            if "miniplan" not in p.name.lower() and short and short in p.name.lower()
        ]
        if candidates:
            spec_path = max(candidates, key=lambda p: p.stat().st_mtime)
            try:
                header = spec_path.read_text(encoding="utf-8", errors="ignore")[:1200]
                for line in header.splitlines():
                    low = line.strip().lower()
                    if low.startswith("- **run id:**") or low.startswith("- **run-id:**"):
                        run_id = line.split(":**", 1)[1].strip()
                    elif low.startswith("- **complexity:**"):
                        complexity = line.split(":**", 1)[1].strip().lower()
            except OSError:
                pass

    # Look for the external review marker. Two filename conventions are
    # acceptable (see iteration-planning.md Step 5): a run-scoped file or
    # the shared state file. Prefer run-scoped if both exist.
    marker_status = "missing"
    marker_detail = ""
    marker_candidates: list[Path] = []
    if run_id:
        marker_candidates.append(iterate_dir / f"{run_id}-external-review.json")
    marker_candidates.append(iterate_dir / "external_review_state.json")
    for candidate in marker_candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        status = data.get("status", "unknown")
        ts_raw = data.get("timestamp", "")
        # Shared marker is stale if it predates the current iterate spec —
        # otherwise it proves review for a prior run, not this one.
        if candidate.name == "external_review_state.json" and spec_path and ts_raw:
            try:
                marker_ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                spec_ts = datetime.fromtimestamp(spec_path.stat().st_mtime, tz=timezone.utc)
                if marker_ts < spec_ts:
                    marker_status = "stale"
                    marker_detail = f"predates spec ({ts_raw[:19]})"
                    continue
            except (ValueError, OSError):
                pass
        marker_status = status
        marker_detail = f"{candidate.name} @ {ts_raw[:19]}" if ts_raw else candidate.name
        break

    lines: list[str] = ["## Current Iterate Progress", ""]
    lines.append(f"- **Branch**: {branch}")
    if run_id:
        lines.append(f"- **Run ID**: {run_id}")
    if spec_path:
        try:
            rel = spec_path.relative_to(project_root).as_posix()
        except ValueError:
            rel = str(spec_path)
        lines.append(f"- **Spec**: {rel}")
    if complexity:
        lines.append(f"- **Complexity**: {complexity}")
    review_line = f"- **External Review Marker**: {marker_status}"
    if marker_detail:
        review_line += f" ({marker_detail})"
    lines.append(review_line)

    replay: list[str] = []
    if complexity in ("medium", "large") and marker_status in ("missing", "stale"):
        replay.append("Step 4 — External LLM Review (marker missing/stale)")
    if git_info.get("uncommitted_changes"):
        replay.append("Finalization (F0–F11) after all mandatory phases pass")

    if replay:
        lines.append("")
        lines.append("### Mandatory replay on Resume")
        lines.append("")
        lines.append("Before dispatching to the handoff's Remaining phase, run these if missing:")
        for item in replay:
            lines.append(f"- {item}")

    lines.append("")
    return lines
