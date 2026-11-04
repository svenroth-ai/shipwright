#!/usr/bin/env python3
"""Compare plan sections with the approved screens (deterministic, conservative).

    uv run check-design-contradictions.py --planning-dir <p> --project-root <p> [--record-decisions]

Prints JSON ``{autonomous, problems, notes, decisions}``. Exit 1 only for an autonomous design
run (brief package or autonomy autonomous/unattended) with problems; interactive runs get notes
and exit 0. ``--record-decisions`` logs every section ``Design decision:`` line to the decision
log once (``write_decision_log.py``; already-logged ones are skipped).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[4] / "shared"
sys.path.insert(0, str(_SHARED / "scripts" / "lib"))

from plan_design_check import design_problems, is_autonomous_design_run, section_decisions  # noqa: E402


def _decisions(planning: Path) -> list[tuple[str, str]]:
    out = []
    for sec in sorted((planning / "sections").glob("*.md")):
        for d in section_decisions(sec.read_text(encoding="utf-8", errors="ignore")):
            out.append((sec.stem, d))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planning-dir", required=True)
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--record-decisions", action="store_true")
    a = ap.parse_args()
    planning, root = Path(a.planning_dir).resolve(), Path(a.project_root).resolve()
    auto = is_autonomous_design_run(root)
    problems, notes = design_problems(planning, root, auto)
    decisions = _decisions(planning)
    if a.record_decisions:
        log = root / ".shipwright" / "agent_docs" / "decision_log.md"
        have = log.read_text(encoding="utf-8", errors="ignore") if log.is_file() else ""
        done: set[tuple[str, str]] = set()
        for sec, d in decisions:
            heading = f"Plan Design Decision — {planning.name}/{sec}"
            if (heading, d[:500]) in done or any(
                    f"**Section:** {heading}" + chr(10) in blk and f"**Decision:** {d[:500]}" in blk
                    for blk in have.split("### ADR-")):
                continue
            rc = subprocess.run([sys.executable, str(_SHARED / "scripts" / "tools" / "write_decision_log.py"),
                                 "--project-root", str(root), "--section", heading, "--commit", "n/a",
                                 "--context", "Section text and approved screen/brief disagreed; autonomous design rule applied",
                                 f"--decision={d[:500]}", "--consequences",
                                 "Build implements the recorded winner without asking"],
                                check=False, stdout=subprocess.DEVNULL).returncode
            done.add((heading, d[:500]))
            if rc != 0:
                problems.append(f"{sec}: decision not logged (write_decision_log.py exit {rc})")
    print(json.dumps({"autonomous": auto, "problems": problems, "notes": notes,
                      "decisions": [{"section": s, "decision": d} for s, d in decisions]}, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
