"""Design brief-mode check, registered in ``design_checks.run_design_checks`` (campaign
brief-driven-run, B3a; BRIEF D8). It applies ONLY to a run whose ``shipwright_run_config.json``
records a ``brief_dir`` -- every other project gets no result from here.

``brief_design_applied`` proves Design took the package instead of re-typing it (prose cannot):

* ``.shipwright/designs/brief-package-applied.json`` exists and its ``package_sha256`` equals the hash
  ``run_config`` recorded for the approved package;
* every planned ``uploads/<mockup>`` exists and matches the package (the package hash's CRLF rule);
* every planned ``screens/NN-id.html`` exists and its ``<!-- Requirements: ... -->`` comments name AT
  LEAST the FR ids recomputed from the screen-map and the FR rows Project minted (a superset: review-loop
  additions are fine, a retyped or dropped id is not -- which also makes a forged marker pointless).

Planning is shared with the writer (``tools/brief_design_plan.py``). No ``lib`` import (ADR-045).
"""

from __future__ import annotations

import json
from pathlib import Path

from .brief_mode_checks import _brief, _guarded
from .common import CheckResult, read_run_config

NAME = "brief_design_applied"
MARKER = ".shipwright/designs/brief-package-applied.json"


def _applied(project_root: Path) -> list[CheckResult]:
    found = _brief(project_root)
    if found is None:
        return []
    from tools.brief_design_plan import applied_file_issues, fr_ids_by_slug, linked_frs, plan_screens

    rel, _raw = found
    cfg = read_run_config(project_root)
    recorded = (cfg.get("brief_package") or {}).get("package_sha256") if isinstance(cfg.get("brief_package"), dict) else None
    marker = project_root / MARKER
    try:
        applied = json.loads(marker.read_text(encoding="utf-8")).get("package_sha256") if marker.is_file() else None
    except (OSError, ValueError, AttributeError):
        applied = None
    if not applied or applied != recorded:
        return [CheckResult(NAME, False, f"{MARKER} is missing or does not hold the package hash recorded in run_config: "
                            "Design did not apply the Brief package (run apply-brief-package.py)")]
    bdir, designs = project_root / rel, project_root / ".shipwright" / "designs"
    screen_map = json.loads((bdir / "screen-map.json").read_text(encoding="utf-8-sig"))
    problems = [i["message"] for i in applied_file_issues(bdir, designs, screen_map)]
    plan, plan_issues = plan_screens(bdir, screen_map, fr_ids_by_slug(project_root))
    problems += [f"{i['screen']}: {i['message']}" for i in plan_issues]
    for item in plan:
        screen = designs / "screens" / item["screen_file"]
        if screen.is_file():
            lost = sorted(set(item["frs"]) - linked_frs(screen.read_text(encoding="utf-8", errors="ignore")))
            if lost:
                problems.append(f"screens/{screen.name} does not link {lost} (the FR ids minted for its screen-map entry)")
    if problems:
        return [CheckResult(NAME, False, "; ".join(problems))]
    return [CheckResult(NAME, True, f"{len(plan)} screen(s) applied from the approved package, uploads intact, minted FRs linked")]


def check_brief_design_applied(project_root: Path) -> list[CheckResult]:
    return _guarded(NAME, _applied, project_root)
