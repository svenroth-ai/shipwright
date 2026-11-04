#!/usr/bin/env python3
"""Decide, by rule, whether an autonomous run may override a failing screenshot check without asking.

    uv run autonomous_override.py --project-root <p>      # prints JSON; exit 0 = allowed, 1 = ask a person

The Test phase's screenshot check is blocking and its validator has no waiver field. In an interactive run a
person decides an override (``single-session-apply --override-reason``, ASK FIRST). In an AUTONOMOUS run (a brief
package governs it, or autonomy is ``autonomous``/``unattended``) the person is not there for a case the run has
already decided, so this rule answers it -- conservatively, and never by loosening the check:

* every ask-level finding of the gate is the screenshot finding (a smoke failure, a missing result... stays a question);
* the check really ran (``status`` ``fail``, ``captured`` true, the standard tolerance) -- an ``error`` is never excused;
* ``shipwright_test_results.json`` carries a ``screenshot_check_accepted_causes`` block in which every cause names a
  documented source: an ADR already COMMITTED in ``decision_log.md`` (one the Test phase wrote itself is not yet), or a
  file of the brief package (``brief:<file>``) plus a ``quotes`` excerpt of it that appears verbatim in that file;
* EVERY failing screen is attributed to those causes only, names the neutralised screenshot pair it was measured on
  (``neutralised``: approved + built, under ``e2e/screenshots/``), and the ratio is RECOMPUTED here from that pair with the test
  plugin's own comparison (the claimed number must match it). The pair is the agent's throw-away copy, so it is BOUND to the check's
  real pair: that pair must reproduce the recorded ratio, and a neutralised side may be neither a real capture nor a byte copy of
  the opposite one. This is a consistency check, not an independent production of the pair;
* the gate verdict is computed HERE from the real Test validator, never taken from the caller: nothing but the screenshot finding;
* ``unattended`` has no override path in apply, so the answer there is ``allowed: false``; for the others this rule only
  replaces the QUESTION: the override itself is the ordinary one and lands in ``validation_overrides[]`` with the reason, and
  apply re-checks under its lock that the verdict holds nothing but the screenshot finding (``AUTONOMOUS_REASON_PREFIX``).

Anything else answers ``allowed: false`` with the reasons, and the run asks as before. Interactive runs never call this.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

_ADR_RE = re.compile(r"^ADR-\d+$")
_FALLBACK_TOLERANCE = 0.15
_SAFE_REL_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")  # no drive letter, no shell metacharacter (".." is caught by the resolve()+is_relative_to containment checks)
_SHOT_PREFIX = "Screenshot check did not pass"
AUTONOMOUS_REASON_PREFIX = "autonomous rule:"
_HERE = Path(__file__).resolve().parent
_TOLERANCE_EPS = 0.01  # the claimed ratio may differ from the recomputed one by rounding only


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def is_autonomous(config) -> bool:
    """A brief package governs the run, or its autonomy is autonomous/unattended (same rule as Plan's design check)."""
    if not isinstance(config, dict):
        return False
    return bool(config.get("brief_package")) or str(config.get("autonomy", "")).strip().lower() in ("autonomous", "unattended")


def _committed_decision_log(root: Path) -> str | None:
    """decision_log.md as COMMITTED at HEAD (None when git cannot say): an ADR the Test phase just wrote is not 'decided earlier'."""
    try:
        proc = subprocess.run(["git", "-C", str(root), "show", "HEAD:./.shipwright/agent_docs/decision_log.md"],
                              capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _load_module(path: Path, name: str):
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:  # noqa: BLE001 - a missing/broken sibling must fail closed, never crash the caller
        sys.modules.pop(name, None)
        return None


def gate_asks(root: Path) -> list[str] | None:
    """The ask-level findings of the real Test-phase validator, or None when it cannot be run (then nothing is allowed)."""
    module = _load_module(_HERE / "phase_validators_late.py", "_shipwright_autonomous_override_late")
    try:
        _ok, issues = module._validate_test(root)
    except Exception:  # noqa: BLE001
        return None
    return [str(i.get("message", "")) for i in issues if i.get("severity") == "ask"]


def _png_compare():
    """The test plugin's ``png_compare``: beside this plugin in the monorepo, else the newest installed version in the plugin cache."""
    here = _HERE.parents[2] / "shipwright-test" / "scripts" / "lib" / "png_compare.py"
    cached = sorted(_HERE.parents[3].glob("shipwright-test/*/scripts/lib/png_compare.py"), key=lambda p: p.parents[2].name) if len(_HERE.parents) > 3 else []
    for path in [here, *reversed(cached)]:
        if path.is_file() and (module := _load_module(path, "_shipwright_autonomous_override_png")) is not None:
            return module
    return None


def _shot_files(root: Path, pair, what: str) -> tuple[list[Path] | None, str | None]:
    """The (approved, built) PNGs a ``{approved, built}`` pair names, contained under e2e/screenshots/."""
    base = (root / "e2e" / "screenshots").resolve()
    files = []
    for side in ("approved", "built"):
        rel = pair.get(side) if isinstance(pair, dict) else None
        if not (isinstance(rel, str) and _SAFE_REL_RE.fullmatch(rel)):
            return None, f"it names no {what} screenshot pair ({side} under e2e/screenshots/)"
        target = (root / rel).resolve()
        if not (target.is_relative_to(base) and target.is_file()):
            return None, f"{what} {side} {rel!r} is not a file under e2e/screenshots/"
        files.append(target)
    return files, None


def _recomputed_ratio(root: Path, att: dict, tolerance: float, scr: dict, used: set) -> tuple[float | None, str | None]:
    """``(ratio, problem)``: the diff ratio recomputed from the attribution's neutralised pair, bound to the check's REAL pair.

    The neutralised pair is the agent's throw-away copy, so it is not taken on trust: the real pair the check recorded must itself
    reproduce the recorded ratio, and a neutralised side may be neither a real capture nor byte-identical to the opposite real capture
    (a copied shot would "neutralise" everything). What remains is a consistency check, not an independent production of the pair."""
    files, why = _shot_files(root, att.get("neutralised"), "neutralised")
    if why:
        return None, why
    real, why = _shot_files(root, scr.get("screenshots"), "real")
    if why:
        return None, why
    capture_dir = (root / "e2e" / "screenshots" / "screenshot-check").resolve()
    if any(f.is_relative_to(capture_dir) for f in files) or set(files) & set(real):
        return None, "a neutralised screenshot lies in the check's own capture folder (any real capture, of any screen, is refused)"
    if tuple(files) in used:
        return None, "two screens share one neutralised pair"
    used.add(tuple(files))
    if files[0].read_bytes() == real[1].read_bytes() or files[1].read_bytes() == real[0].read_bytes():
        return None, "a neutralised screenshot is a copy of the opposite real capture"
    compare = _png_compare()
    if compare is None:
        return None, "the test plugin's png_compare is not available to recompute the ratio"
    seen = compare.compare_images(real[0], real[1], tolerance).get("diff_ratio")
    if not isinstance(seen, (int, float)) or abs(seen - float(scr.get("diff_ratio") or 0)) > _TOLERANCE_EPS:
        return None, "the real screenshot pair does not reproduce the check's recorded ratio"
    result = compare.compare_images(files[0], files[1], tolerance)
    ratio = result.get("diff_ratio")
    if result.get("status") == "error" or not isinstance(ratio, (int, float)):
        return None, f"the neutralised pair cannot be compared: {result.get('error')}"
    return float(ratio), None


def _quoted(quote, text: str) -> bool:
    """A 12+ character excerpt that appears verbatim (whitespace-normalised) in ``text``."""
    norm = " ".join(str(quote or "").split())
    return len(norm) >= 12 and norm in " ".join(text.split())


def _source_problem(root: Path, config: dict, ref, quote=None) -> str | None:
    """Why a cause's source is not a documented earlier decision (None = documented)."""
    if not isinstance(ref, str) or not ref.strip():
        return "no source"
    ref = ref.strip()
    if _ADR_RE.match(ref):
        text = _committed_decision_log(root)
        if text is None:
            return f"{ref}: decision_log.md at HEAD cannot be read (not committed yet?)"
        m = re.search(rf"^###\s+{re.escape(ref)}\b[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)", text, re.M | re.S)
        if not m:
            return f"{ref} is not in the committed decision_log.md"
        return None if _quoted(quote, m.group(1)) else f"{ref!r}: the cause needs a `quotes` excerpt (12+ characters) found verbatim in that ADR"
    if ref.startswith("brief:"):
        brief_dir = config.get("brief_dir")
        rel = ref[len("brief:"):].strip()
        if not (isinstance(brief_dir, str) and brief_dir and rel and _SAFE_REL_RE.fullmatch(rel)):
            return f"{ref!r} does not name a file of the brief package"
        base = (root / brief_dir).resolve()
        target = (base / rel).resolve()
        if target.is_relative_to(base) and target.relative_to(base).parts[:1] == ("evidence",):
            return f"{ref!r} is in the package's unhashed evidence/ folder: not a documented source"
        if not (target.is_relative_to(base) and target.is_file()):
            return f"{ref!r} is not a file of the brief package"
        return None if _quoted(quote, target.read_text(encoding="utf-8-sig", errors="ignore")) else \
            f"{ref!r}: the cause needs a `quotes` excerpt (12+ characters) found verbatim in that file"
    return f"{ref!r} is neither an ADR id nor brief:<file>"


def decide_screenshot_override(project_root: Path, ask_messages: list[str] | None = None, *, gate: list[str] | None = None) -> dict:
    """``{allowed, reasons[], reason?}``; ``reason`` is the text for ``--override-reason`` when allowed.

    The gate's findings come from the real validator (``gate_asks``); ``ask_messages`` can only ADD findings. ``gate`` replaces the
    validator call (tests)."""
    root = Path(project_root)
    no: list[str] = []
    config = _read(root / "shipwright_run_config.json")
    if not is_autonomous(config):
        return {"allowed": False, "reasons": ["not an autonomous run: a person decides an override"]}
    if str(config.get("autonomy", "")).strip().lower() not in ("guided", "autonomous"):
        return {"allowed": False, "reasons": ["autonomy has no override path in single-session-apply (only guided/autonomous): a person decides"]}
    computed = gate_asks(root) if gate is None else gate
    if computed is None:
        return {"allowed": False, "reasons": ["the Test-phase validator could not be run: the gate verdict is unknown"]}
    messages = [*computed, *(str(m) for m in (ask_messages or []))]
    if not any(m.startswith(_SHOT_PREFIX) for m in messages):
        no.append("the gate raised no screenshot finding: nothing to override by this rule")
    others = [m for m in messages if not m.startswith(_SHOT_PREFIX)]
    if others:
        no.append(f"the gate also raised other findings that need a person: {others[:2]}")
    results = _read(root / "shipwright_test_results.json")
    shot = results.get("screenshot_check") if isinstance(results, dict) else None
    block = results.get("screenshot_check_accepted_causes") if isinstance(results, dict) else None
    if not isinstance(shot, dict) or shot.get("applies") is not True or shot.get("status") != "fail":
        return {"allowed": False, "reasons": no + ["screenshot_check is not a recorded `fail` (a pass needs no override; an error is never excused)"]}
    tolerance = shot.get("tolerance")
    if shot.get("captured") is not True or not isinstance(tolerance, (int, float)) or tolerance != _FALLBACK_TOLERANCE:
        return {"allowed": False, "reasons": no + ["the screenshot check was not a fresh capture at the standard tolerance"]}
    if not isinstance(block, dict) or not isinstance(block.get("accepted_causes"), dict) or not block["accepted_causes"]:
        return {"allowed": False, "reasons": no + ["no `screenshot_check_accepted_causes.accepted_causes` recorded"]}
    causes = block["accepted_causes"]
    sources = block.get("sources") if isinstance(block.get("sources"), dict) else {}
    quotes = block.get("quotes") if isinstance(block.get("quotes"), dict) else {}
    for cid in causes:
        if not (isinstance(cid, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,20}", cid)):
            no.append(f"cause id {cid!r} is not a short plain identifier")
            continue
        why = _source_problem(root, config, sources.get(cid), quotes.get(cid))
        if why:
            no.append(f"cause {cid!r}: {why}")
    attributed = {s.get("mockup"): s for s in block.get("screens", []) if isinstance(s, dict)}
    names, used = set(), set()
    screens = shot.get("screens")
    if not isinstance(screens, list) or not screens:
        no.append("screenshot_check lists no screens")
        screens = []
    for scr in screens:
        if not isinstance(scr, dict):
            no.append("screenshot_check.screens holds a non-object entry")
            continue
        if scr.get("status") == "pass":
            continue
        mockup = scr.get("mockup")
        a = attributed.get(mockup)
        if scr.get("status") != "fail" or a is None:
            no.append(f"screen {mockup!r} ({scr.get('status')}) has no attribution to accepted causes")
            continue
        listed = a.get("causes")
        ratio = a.get("attributed_diff_ratio_without_accepted_causes")
        if not isinstance(listed, list) or not listed or not set(listed) <= {str(c) for c in causes}:
            no.append(f"screen {mockup!r}: its causes are not all accepted causes")
        elif (not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or not math.isfinite(ratio)
              or ratio < 0 or ratio > _FALLBACK_TOLERANCE):
            no.append(f"screen {mockup!r}: still {ratio!r} over the tolerance without the accepted causes (a real mismatch)")
        elif a.get("real_diff_ratio") != scr.get("diff_ratio"):
            no.append(f"screen {mockup!r}: the attribution is for a different run (ratio differs from the check's)")
        else:
            again, why = _recomputed_ratio(root, a, float(tolerance), scr, used)
            if why:
                no.append(f"screen {mockup!r}: {why}")
            elif again > _FALLBACK_TOLERANCE or abs(again - ratio) > _TOLERANCE_EPS:
                no.append(f"screen {mockup!r}: recomputed from its neutralised pair the ratio is {again}, not the claimed {ratio} (or over the tolerance)")
            else:
                names.add(str(mockup))
    if not names:
        no.append("no failing screen is attributed to the accepted causes")
    if no:
        return {"allowed": False, "reasons": no}
    # only validated ids and sources go into the reason: it is pasted into a shell command by the coordinator
    listing = "; ".join(f"cause {cid} [{str(sources[cid]).strip()}]" for cid in causes)
    return {"allowed": True, "reasons": [], "screens": sorted(names), "reason": (
        f"{AUTONOMOUS_REASON_PREFIX} screenshot check fails on {len(names)} screen(s) only for causes decided earlier ({listing}); "
        f"without them every screen is within the {_FALLBACK_TOLERANCE} tolerance")}


def main() -> int:
    p = argparse.ArgumentParser(description="Autonomous-run override rule for the screenshot check")
    p.add_argument("--project-root", required=True)
    p.add_argument("--ask-message", action="append", default=[], help="an EXTRA ask-level finding (the gate is computed here)")
    args = p.parse_args()
    out = decide_screenshot_override(Path(args.project_root), args.ask_message)
    print(json.dumps(out, indent=2))
    return 0 if out["allowed"] else 1


if __name__ == "__main__":
    sys.exit(main())
