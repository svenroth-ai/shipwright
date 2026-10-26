"""Chat-first design check, registered in ``design_checks.run_design_checks`` (campaign brief-driven-run,
B3b; BRIEF D8). It applies ONLY to a verified Brief package whose ``brief.json`` says ``ux_shape: chat-first``.

``brief_chat_first_applied``: ``chat-map.json`` still agrees with ``screen-map.json`` (every chat-only capability names a
screen that lists its requirements), each such pane-state screen still links the FR ids minted for them (first
``Requirements`` comment; extra ids are fine) and every golden path still has its flow mockup in ``flows/``.
It runs beside ``brief_design_applied`` (package verification, marker, uploads); planning is shared with the writer
(``tools/brief_chat_plan.py``). No ``lib`` import (ADR-045).
"""

from __future__ import annotations

import json
from pathlib import Path

from .brief_mode_checks import _guarded, verified_package
from .common import CheckResult

NAME = "brief_chat_first_applied"


def _applied(project_root: Path) -> list[CheckResult]:
    from tools.brief_chat_plan import applied_problems
    from tools.brief_design_plan import fr_ids_by_slug, plan_screens

    try:
        verified = verified_package(project_root)
    except Exception as exc:  # noqa: BLE001 -- BriefRefused is a class per loader: duck-typed
        if not hasattr(exc, "as_dict"):
            raise
        return []  # brief_design_applied reports a package that does not verify
    if not verified.get("package"):
        return []
    bdir = project_root / str(verified["brief_dir"]).replace("\\", "/").strip("/")  # as brief_design_applied
    if json.loads((bdir / "brief.json").read_text(encoding="utf-8-sig")).get("ux_shape") != "chat-first":
        return []
    screen_map = json.loads((bdir / "screen-map.json").read_text(encoding="utf-8-sig"))
    by_slug = fr_ids_by_slug(project_root)
    plan, _issues = plan_screens(bdir, screen_map, by_slug)
    problems = applied_problems(bdir, project_root / ".shipwright" / "designs", screen_map, plan, by_slug)
    if problems:
        return [CheckResult(NAME, False, "; ".join(problems))]
    return [CheckResult(NAME, True, "chat-only capabilities have their pane-state screens and every golden path its flow")]


def check_brief_chat_first_applied(project_root: Path) -> list[CheckResult]:
    return _guarded(NAME, _applied, project_root)
