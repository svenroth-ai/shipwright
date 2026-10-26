"""Design brief-mode check, registered in ``design_checks.run_design_checks`` (campaign
brief-driven-run, B3a; BRIEF D8). It applies ONLY to a run whose ``shipwright_run_config.json``
records a ``brief_dir`` or a ``brief_package`` -- every other project gets no result from here.

``brief_design_applied`` checks that Design's output still rests on the approved package (it does NOT
prove the screens came from the tool). The package must still verify first (``verify_run_config``), then:

* ``.shipwright/designs/brief-package-applied.json`` exists and its ``package_sha256`` equals the hash
  ``run_config`` recorded for the approved package;
* every planned ``uploads/<mockup>`` exists and matches the package (the package hash's CRLF rule);
* every planned ``screens/NN-id.html`` exists and its ``<!-- Requirements: ... -->`` comments name AT
  LEAST the FR ids recomputed from the screen-map and the FR rows Project minted (a superset, read like the manifest does: the FIRST comment; review-loop
  additions are fine, a retyped or dropped id is not).

Lifetime: the approved package stays the contract for the life of the project; a later FR/screen rename turns this red
by design -- changing it means a new package and a re-apply.

Planning is shared with the writer (``tools/brief_design_plan.py``). No ``lib`` import (ADR-045).
"""

from __future__ import annotations

import json
from pathlib import Path

from .brief_mode_checks import _guarded, verified_package
from .common import CheckResult

NAME = "brief_design_applied"


def _mentions_brief(project_root: Path) -> bool:
    try:
        raw = (project_root / "shipwright_run_config.json").read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return False
    return "brief_dir" in raw or "brief_package" in raw


def _applied(project_root: Path) -> list[CheckResult]:
    from tools.brief_design_plan import MARKER_NAME, applied_file_issues, fr_ids_by_slug, linked_frs, plan_screens

    try:  # the SAME parser as the resume check (utf-8-sig, key presence); the package must verify BEFORE anything is read from it
        verified = verified_package(project_root)
    except Exception as exc:  # noqa: BLE001 -- BriefRefused is a class per loader: duck-typed
        if not hasattr(exc, "as_dict"):
            raise
        if exc.code == "bad_run_config" and not _mentions_brief(project_root):  # a malformed config of a non-brief project
            return []
        return [CheckResult(NAME, False, f"the recorded Brief package does not verify: {exc.code}: {exc.message}")]
    if not verified.get("package"):  # neither brief_dir nor brief_package: not a brief run
        return []
    rel = str(verified["brief_dir"]).replace("\\", "/").strip("/")  # a verified package always has its brief_dir
    recorded = verified.get("package_sha256")
    marker_rel = f".shipwright/designs/{MARKER_NAME}"
    marker = project_root / marker_rel
    try:
        applied = json.loads(marker.read_text(encoding="utf-8")).get("package_sha256") if marker.is_file() else None
    except (OSError, ValueError, AttributeError):
        applied = None
    if not applied or applied != recorded:
        return [CheckResult(NAME, False, f"{marker_rel} is missing or does not hold the package hash recorded in run_config: "
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
    return [CheckResult(NAME, True, f"{len(plan)} screen(s) mapped by the approved package, uploads intact, minted FRs linked")]


def check_brief_design_applied(project_root: Path) -> list[CheckResult]:
    return _guarded(NAME, _applied, project_root)
