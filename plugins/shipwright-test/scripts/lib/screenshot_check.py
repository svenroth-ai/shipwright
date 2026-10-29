#!/usr/bin/env python3
"""Screenshot check: the BLOCKING Test-phase comparison of built screens with the approved design screens.

Campaign brief-driven-run, B3c (D9). It sits BESIDE the non-blocking structural step
(``design_fidelity_check.py``, Step 3.7) and does not touch it.

    uv run screenshot_check.py --cwd <project_root> --base-url http://localhost:3000

Applies ONLY when Design applied a Brief package (``.shipwright/designs/brief-package-applied.json``).
Any other project: ``{"applies": false}``, exit 0 -- today's behaviour, unchanged.

Per screen in ``.shipwright/designs/screen-routes.json`` the approved design screen is the byte-identical copy
in ``.shipwright/designs/uploads/`` (found through the package's ``screen-map.json`` by the screen's NN
prefix, else by the same file name). The mockup and the built route are screenshotted by the SAME
Playwright run at the SAME viewport, then compared with ``png_compare`` (metric + tolerance recorded).

A screen that is a STATE of one served page (a board tab, a pane) has no route of its own: give its entry the page's
route plus ``steps`` (``{"click": sel}``, ``{"fill": [sel, text]}``, ``{"wait_for": sel}``), run on the built page before the shot.

Exit codes: 0 = every screen passed (or the check does not apply) -- 1 = at least one screen is a
visible mismatch (``fail``) -- 2 = the check could not run or a screen could not be compared (``error``).
Both 1 and 2 BLOCK. Nothing here waives, edits a mockup or approves anything.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling by unique name: `lib` is ambiguous across roots (ADR-045)
import png_compare  # noqa: E402

MARKER = "brief-package-applied.json"
VIEWPORT = (1280, 800)
_NN_RE = re.compile(r"^(\d{1,3})-")
_DYNAMIC_RE = re.compile(r"[\[\]:*{}]")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _approved_for(root: Path, mockup: str, screen_map: dict) -> Path | None:
    """The approved mockup in ``uploads/`` for a screen-routes entry (NN prefix via screen-map, else same name)."""
    designs = root / ".shipwright" / "designs"
    name = Path(mockup).name
    m = _NN_RE.match(name)
    screens = screen_map.get("screens") if isinstance(screen_map, dict) else None
    if m and isinstance(screens, list) and 1 <= int(m.group(1)) <= len(screens):
        entry = screens[int(m.group(1)) - 1]
        upload = designs / "uploads" / Path(str(entry.get("mockup") or "") if isinstance(entry, dict) else "").name
        if upload.is_file():
            return upload
    same = designs / "uploads" / name
    return same if same.is_file() else None


MAX_STEPS = 10
_STEP_KEYS = {"click": str, "wait_for": str, "fill": list}


def _bad_steps(steps) -> str | None:
    """Why ``steps`` cannot run (None = fine): a list of one-key dicts click/wait_for (selector) or fill ([selector, text])."""
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        return f"'steps' must be a list of at most {MAX_STEPS}"
    for st in steps:
        key = next(iter(st), None) if isinstance(st, dict) and len(st) == 1 else None
        val = st.get(key) if key else None
        ok = key in _STEP_KEYS and isinstance(val, _STEP_KEYS[key]) and val != "" and (
            key != "fill" or (len(val) == 2 and isinstance(val[0], str) and val[0] != "" and isinstance(val[1], (str, int, float))))
        if not ok:
            return f"step {st!r} is not click / wait_for (selector) or fill ([selector, text])"
    return None


def _route_entries(data) -> tuple[str, list]:
    """``(base_url, entries)`` of screen-routes.json: Design writes a flat ``{mockup: route}`` dict, Build/others the nested form."""
    if isinstance(data, dict) and "screens" in data:
        return str(data.get("base_url") or ""), data["screens"] if isinstance(data["screens"], list) else []
    if isinstance(data, dict):
        return "", [{"mockup": k, **(v if isinstance(v, dict) else {"route": v})} for k, v in data.items()]
    return "", []


def _builder_file(root: Path, mockup: str) -> Path | None:
    """The file the builder worked from: the screen as Design left it (review-loop edits count), else None."""
    designs = root / ".shipwright" / "designs"
    for cand in (designs / mockup, designs / "screens" / Path(mockup).name):
        if Path(mockup).name and cand.is_file():
            return cand
    return None


def _playwright_dirs(root: Path) -> list[Path]:
    """Where playwright_setup may have installed Playwright: the root, or the service dir holding playwright.config.ts."""
    found = [p.parent for p in sorted(root.glob("*/playwright.config.ts")) + sorted(root.glob("*/*/playwright.config.ts"))
             if "node_modules" not in p.parts]
    return [d for d in found if d != root]


def _screen_map(root: Path) -> dict:
    cfg = _read_json(root / "shipwright_run_config.json")
    brief_dir = cfg.get("brief_dir") if isinstance(cfg, dict) else None
    if not isinstance(brief_dir, str) or not brief_dir:
        return {}
    data = _read_json(root / brief_dir / "screen-map.json")
    return data if isinstance(data, dict) else {}


def _capture(root: Path, jobs: list[dict], timeout: int) -> str | None:
    """Run the Playwright capture; ``None`` = all captured, else the reason it did not work."""
    node = shutil.which("node")
    if not node:
        return "node is not on PATH (Playwright needs it)"
    jobs_file = root / "e2e" / "screenshots" / "screenshot-check" / "jobs.json"
    jobs_file.write_text(json.dumps(jobs), encoding="utf-8")
    script = Path(__file__).resolve().parent / "screenshot_capture.mjs"
    try:
        proc = subprocess.run(
            [node, str(script), "--project", str(root), "--jobs", str(jobs_file),
             "--width", str(VIEWPORT[0]), "--height", str(VIEWPORT[1]),
             *[a for d in _playwright_dirs(root) for a in ("--search", str(d))]],
            cwd=str(root), capture_output=True, text=True, timeout=timeout, encoding="utf-8",
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"capture did not run: {exc}"
    try:
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return f"capture output unreadable: {(proc.stderr or proc.stdout)[:300]}"
    errs = out.get("errors") or []
    return "; ".join(f"{Path(e.get('out', '')).name}: {e.get('error')}" for e in errs) or (None if out.get("ok") else "capture failed")


def run_screenshot_check(root: Path, base_url: str | None = None, tolerance: float = png_compare.TOLERANCE,
                         capture: bool = True, timeout: int | None = None) -> dict:
    root = Path(root)
    designs = root / ".shipwright" / "designs"
    if not (designs / MARKER).is_file():
        return {"applies": False, "status": "skipped", "reason": "no Brief package was applied by Design"}
    base = {"applies": True, "metric": png_compare.METRIC, "tolerance": tolerance, "viewport": list(VIEWPORT), "captured": capture}
    data = _read_json(designs / "screen-routes.json")
    file_base_url, entries = _route_entries(data)
    if not entries:
        return {**base, "status": "error", "screens": [], "error": "screen-routes.json is missing or lists no screens"}
    base_url = (base_url or file_base_url).rstrip("/")
    if capture and not base_url:
        return {**base, "status": "error", "screens": [], "error": "no running app: pass --base-url"}

    shots = root / "e2e" / "screenshots" / "screenshot-check"
    for side in ("approved", "built"):
        (shots / side).mkdir(parents=True, exist_ok=True)
        if capture:  # a fresh capture never sits next to the previous run's pictures
            for old in (shots / side).glob("*.png"):
                old.unlink()
    smap = _screen_map(root)
    results: list[dict] = []
    jobs: list[dict] = []
    for idx, entry in enumerate(entries, start=1):
        mockup = str(entry.get("mockup") or "") if isinstance(entry, dict) else ""
        route = str(entry.get("sample_route") or entry.get("route") or "") if isinstance(entry, dict) else ""
        stem = f"{idx:02d}-{Path(mockup).stem}" if Path(mockup).stem else ""  # unique per entry: same-named mockups never share a file
        approved = _approved_for(root, mockup, smap)
        source = _builder_file(root, mockup) or approved
        res = {"mockup": mockup, "route": route, "status": "pending", "stem": stem, **({"approved": approved} if approved else {})}
        if not stem or source is None:
            res.update(status="error", error=f"no approved design screen in screens/ or uploads/ for {mockup!r}")
        elif not route.startswith("/") or _DYNAMIC_RE.search(route):
            res.update(status="error", error=f"route {route!r} is not a concrete path: add a 'sample_route' to its screen-routes.json entry")
        elif "steps" in entry and (steps := entry["steps"]) is not None and (why := _bad_steps(steps)):
            res.update(status="error", error=f"screen {mockup!r}: {why}")
        else:
            res["compared_with"] = source.relative_to(root).as_posix()
            if capture:
                jobs += [{"url": source.resolve().as_uri(), "out": str(shots / "approved" / f"{stem}.png")},
                         {"url": f"{base_url}{route}", "out": str(shots / "built" / f"{stem}.png"), **({"steps": steps} if entry.get("steps") else {})}]
        results.append(res)
    covered = {res["approved"].name for res in results if "approved" in res}
    for entry in (smap.get("screens") if isinstance(smap.get("screens"), list) else []):
        mock = Path(str(entry.get("mockup") or "")).name if isinstance(entry, dict) else ""
        if mock and mock not in covered:
            has_upload = (root / ".shipwright" / "designs" / "uploads" / mock).is_file()
            results.append({"mockup": mock, "route": "", "status": "error", "error": (
                f"package screen {mock!r} has no entry in screen-routes.json: it was never built or mapped" if has_upload
                else f"package screen {mock!r} has no entry in screen-routes.json and no approved design screen in uploads/")})
    failure = _capture(root, jobs, timeout or 60 + 45 * len(jobs) + 15 * sum(len(j.get("steps", [])) for j in jobs)) if capture and jobs else None
    for res in results:
        if res["status"] != "pending":
            continue
        stem = res.pop("stem")
        res.pop("approved", None)
        a, b = shots / "approved" / f"{stem}.png", shots / "built" / f"{stem}.png"
        res.update(png_compare.compare_images(a, b, tolerance) if a.is_file() and b.is_file()
                   else {"status": "error", "error": f"no screenshot pair captured{': ' + failure if failure else ''}"})
        res["screenshots"] = {"approved": a.relative_to(root).as_posix(), "built": b.relative_to(root).as_posix()}
    for res in results:
        res.pop("approved", None)
        res.pop("stem", None)
    states = {r["status"] for r in results}
    status = "error" if "error" in states else "fail" if "fail" in states else "pass"
    return {**base, "status": status, "screens": results, "passed": sum(r["status"] == "pass" for r in results),
            "total": len(results), **({"capture_error": failure} if failure else {})}


def main() -> int:
    p = argparse.ArgumentParser(description="Blocking screenshot check: built screens vs approved design screens (Brief package only)")
    p.add_argument("--cwd", required=True, help="Project root")
    p.add_argument("--base-url", help="Running app, e.g. http://localhost:3000")
    p.add_argument("--tolerance", type=float, default=png_compare.TOLERANCE)
    p.add_argument("--no-capture", action="store_true", help="Compare screenshots already in e2e/screenshots/screenshot-check/")
    args = p.parse_args()
    result = run_screenshot_check(Path(args.cwd).resolve(), args.base_url, args.tolerance, capture=not args.no_capture)
    print(json.dumps(result, indent=2))
    return {"fail": 1, "error": 2}.get(result["status"], 0)


if __name__ == "__main__":
    sys.exit(main())
