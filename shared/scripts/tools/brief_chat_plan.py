"""What Design adds for a chat-first Brief package, shared by its writer and its verifier (campaign
brief-driven-run, B3b; BRIEF D8).

``chat-map.json`` (version 1) lists the chat-only capabilities and the golden paths of the app::

    {"version": 1,
     "capabilities": [{"id": "fetch", "command": "fetch new matches",
                       "requirements": ["fetch-new-matches"], "screen": "board-new"}],
     "golden_paths": [{"id": "triage", "title": "Triage a thread",
                       "steps": [{"say": "fetch new matches", "screen": "board-new"}]}]}

ONE rule ties it to the rest of the package: every ``screen`` names a ``screen-map.json`` entry, and a
capability's ``requirements`` (capability slugs) are a subset of the ``requirements`` of ITS screen. That
screen is the capability's pane-state screen; the FR ids it links come from ``brief_design_plan``
(the ids Project minted), so this module never sees an FR id it did not read from there.

* the design plugin's ``apply-brief-package.py`` writes one flow mockup per golden path (``flows/NN-id.html``,
  generated, deterministic, standalone, no navigation markup);
* ``verifiers/brief_chat_checks.py`` re-derives the same plan to prove the capabilities still have their screens.

No ``lib`` import (the verifier runs inside other plugins' validators, ADR-045).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from tools.brief_design_plan import linked_frs, screen_file_name
from tools.grill_trace_fr_coverage import slugify

CHAT_MAP = "chat-map.json"
VERSION = 1


def _issue(path: str, message: str) -> dict:
    return {"code": "bad_chat_map", "screen": path, "message": message}


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _screens(screen_map: dict) -> dict[str, set[str]]:
    """``{screen id slug: requirement slugs}`` of the well-formed screen-map entries."""
    out: dict[str, set[str]] = {}
    for entry in screen_map.get("screens") or []:
        reqs = entry.get("requirements") if isinstance(entry, dict) else None
        if isinstance(reqs, list) and all(isinstance(r, str) for r in reqs):
            out[slugify(str(entry.get("id") or ""))] = {slugify(r) for r in reqs}
    return out


def read_chat_map(bdir: Path) -> tuple[dict | None, list[dict]]:
    try:
        data = json.loads((bdir / CHAT_MAP).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, [_issue(CHAT_MAP, f"{CHAT_MAP} is not readable JSON: {type(exc).__name__}")]
    if not isinstance(data, dict):
        return None, [_issue(CHAT_MAP, f"{CHAT_MAP} must be a JSON object")]
    return data, []


def chat_map_issues(chat_map: dict, screen_map: dict) -> list[dict]:
    screens = _screens(screen_map)
    out: list[dict] = []
    if chat_map.get("version") != VERSION:
        out.append(_issue(CHAT_MAP, f"version must be {VERSION}"))
    caps, paths = chat_map.get("capabilities"), chat_map.get("golden_paths")
    for key, rows in (("capabilities", caps), ("golden_paths", paths)):
        if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
            out.append(_issue(key, f"{key} must be a non-empty list of objects"))
    seen: set[str] = set()
    for i, cap in enumerate(caps if isinstance(caps, list) else [], start=1):
        if not isinstance(cap, dict):
            continue
        cid, where = slugify(str(cap.get("id") or "")), f"capabilities[{i}]"
        reqs, screen = cap.get("requirements"), slugify(str(cap.get("screen") or ""))
        if not cid or cid in seen:
            out.append(_issue(where, "id is empty or repeated"))
        seen.add(cid)
        if not _text(cap.get("command")):
            out.append(_issue(where, "command must be the chat phrase, a non-empty string"))
        good_reqs = isinstance(reqs, list) and bool(reqs) and all(_text(r) for r in reqs)
        if not good_reqs:
            out.append(_issue(where, "requirements must be a non-empty list of capability slugs"))
        if screen not in screens:
            out.append(_issue(where, f"screen {cap.get('screen')!r} is not a screen-map id (a chat-only capability needs its pane-state screen)"))
        elif good_reqs:
            lost = sorted({slugify(r) for r in reqs} - screens[screen])
            if lost:
                out.append(_issue(where, f"screen {screen!r} does not list {lost} in its screen-map requirements"))
    seen = set()
    for i, path in enumerate(paths if isinstance(paths, list) else [], start=1):
        if not isinstance(path, dict):
            continue
        pid, where, steps = slugify(str(path.get("id") or "")), f"golden_paths[{i}]", path.get("steps")
        if not pid or pid in seen:
            out.append(_issue(where, "id is empty or repeated"))
        seen.add(pid)
        if not _text(path.get("title")):
            out.append(_issue(where, "title must be a non-empty string"))
        if not (isinstance(steps, list) and steps and all(isinstance(s, dict) for s in steps)):
            out.append(_issue(where, "steps must be a non-empty list of objects"))
            continue
        for n, step in enumerate(steps, start=1):
            if not _text(step.get("say")):
                out.append(_issue(f"{where}.steps[{n}]", "say must be the chat message, a non-empty string"))
            if slugify(str(step.get("screen") or "")) not in screens:
                out.append(_issue(f"{where}.steps[{n}]", f"screen {step.get('screen')!r} is not a screen-map id"))
    return out


def flow_file_name(idx: int, path: dict) -> str:
    return f"{idx:02d}-{slugify(str(path.get('id') or ''))}.html"


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #f6f7f9; color: #111; }}
h1 {{ font-size: 20px; }}
.step {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 12px 0; }}
.chat-bubble {{ background: #fff; border: 1px solid #d0d5dd; border-radius: 12px; padding: 12px; }}
.pane-ref {{ background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 8px; padding: 12px; }}
.pane-ref iframe {{ width: 100%; height: 420px; border: 1px solid #c7d2fe; background: #fff; margin-top: 8px; }}
.step-no {{ font-weight: 600; color: #444; }}
</style>
</head>
<body>
<h1>{title}</h1>
{steps}
</body>
</html>
"""


def flow_page(path: dict, screen_files: dict[str, str], panes: dict[str, str] | None = None) -> str:
    """The flow mockup of one golden path: per step the chat message and the pane-state screen it shows
    (the approved mockup, inlined as an escaped ``srcdoc`` of a sandboxed frame: standalone, no external reference)."""
    rows = []
    for n, step in enumerate(path["steps"], start=1):
        key = slugify(str(step["screen"]))
        frame = (f'<iframe sandbox title="{html.escape(str(step["screen"]))}" srcdoc="{html.escape((panes or {}).get(key, ""))}"></iframe>'
                 if (panes or {}).get(key) else "")
        rows.append(f'<div class="step"><div class="chat-bubble"><span class="step-no">Step {n}.</span> '
                    f'{html.escape(str(step["say"]))}</div>'
                    f'<div class="pane-ref">Pane: {html.escape(str(step["screen"]))} ({html.escape(screen_files.get(key, ""))}){frame}</div></div>')
    return _PAGE.format(title=html.escape(str(path["title"])), steps=chr(10).join(rows))


def plan_flows(bdir: Path, screen_map: dict) -> tuple[list[dict], list[dict]]:
    """``(flow files to write, issues)`` for a chat-first package."""
    chat_map, issues = read_chat_map(bdir)
    if chat_map is None:
        return [], issues
    issues = chat_map_issues(chat_map, screen_map)
    if issues:
        return [], issues
    files = {slugify(str(e.get("id") or "")): screen_file_name(i, e)
             for i, e in enumerate(screen_map.get("screens") or [], start=1) if isinstance(e, dict)}
    panes = {}
    for e in screen_map.get("screens") or []:
        try:
            panes[slugify(str(e.get("id") or ""))] = (bdir / "mockups" / str(e.get("mockup") or "")).read_text(encoding="utf-8-sig", errors="replace")
        except (OSError, AttributeError):
            pass  # plan_screens reports a missing or malformed mockup
    return [{"file": flow_file_name(i, p), "html": flow_page(p, files, panes)}
            for i, p in enumerate(chat_map["golden_paths"], start=1)], []


def applied_problems(bdir: Path, designs: Path, screen_map: dict, plan: list[dict], by_slug: dict[str, list[str]]) -> list[str]:
    """Why an applied chat-first design no longer matches its ``chat-map.json`` (empty = fine)."""
    chat_map, issues = read_chat_map(bdir)
    if chat_map is not None:
        issues = chat_map_issues(chat_map, screen_map)
    if chat_map is None or issues:
        return [f"{i['screen']}: {i['message']}" for i in issues]
    problems: list[str] = []
    placed = {item["id"]: item for item in plan}
    for cap in chat_map["capabilities"]:
        item = placed.get(slugify(str(cap["screen"])))
        if item is None:
            problems.append(f"capability {cap['id']!r}: its screen {cap['screen']!r} is not a planned screen")
            continue
        slugs = [slugify(r) for r in cap["requirements"]]
        problems += [f"capability {cap['id']!r}: requirement {s!r} matches {len(by_slug.get(s, ()))} minted FR rows (exactly one expected)"
                     for s in slugs if len(by_slug.get(s, ())) != 1]
        needed = {by_slug[s][0] for s in slugs if len(by_slug.get(s, ())) == 1}
        screen = designs / "screens" / item["screen_file"]
        lost = sorted(needed - linked_frs(screen.read_text(encoding="utf-8", errors="ignore"))) if screen.is_file() else sorted(needed)
        if lost:
            problems.append(f"capability {cap['id']!r}: screens/{item['screen_file']} does not link {lost}")
    problems += [f"flows/{flow_file_name(i, p)} is missing (golden path {p['id']!r})"
                 for i, p in enumerate(chat_map["golden_paths"], start=1)
                 if not (designs / "flows" / flow_file_name(i, p)).is_file()]
    return problems
