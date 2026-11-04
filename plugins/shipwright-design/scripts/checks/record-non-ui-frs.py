#!/usr/bin/env python3
"""Record the Brief package's non-UI capabilities as ``## Non-UI FRs`` (autonomous runs, no question).

    uv run record-non-ui-frs.py --project-root <path>

After ``apply-brief-package.py`` a minted FR that no screen-map entry covers is ``unmapped`` and the ``fr-coverage`` gate stays red.
In an AUTONOMOUS run (a brief package governs it, or autonomy is autonomous/unattended) the answer is already in the package for
a capability whose ``brief.md`` section says it has no screen: the section states ``UI: none`` on a line of its own. Only that
explicit marker counts: a missing mockup reference is NOT a statement that there is no screen (the author may have forgotten it). Those FRs are written under ``## Non-UI FRs`` in ``design-manifest.md`` citing ONE decision-log entry
(``write_decision_log.py``) that names them; the ``fr-coverage`` gate then honours them. Nothing else changes: no screen is
invented, the package and ``uploads/`` stay untouched.

A capability without the marker (even with a ``Source:`` line that names no mockup), one whose section names a mockup or screen
that was never mapped (the package contradicts itself), or one with no section at all stays a question (``ask`` in the output, exit 1). An interactive run is not
touched at all: ``action: "ask"``, nothing written (the operator-authored entry in upload-mode.md stays the way).

Prints JSON ``{autonomous, action, recorded[], ask[], adr}``. Exit 0 = nothing left to ask, 1 = something left, 2 = cannot run.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SHARED = Path(__file__).resolve().parents[4] / "shared"


_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
_UI_NONE_RE = re.compile(r"^\s*[-*]?\s*ui\s*:\s*none\s*\.?\s*$", re.I | re.M)  # the brief format's one marker
_SCREEN_REF_RE = re.compile(r"mockup|wireframe|\bscreens?\b|\b\d{2}-[\w-]+\.html\b", re.I)
_MOCKUP_REF_RE = re.compile(r"mockup|wireframe|\bfigma\b|\b\d{2}-[\w-]+\.html\b", re.I)  # a concrete screen reference (the bare word "screen" is prose)
_DUP_MARK = "<<duplicate-heading>>"
_PLACEHOLDER_RE = re.compile(r"replace with a real FR id", re.I)
_SLUG_COLLAPSE_RE = re.compile(r"[^a-z0-9]+")
_MAX = 500  # ADR field cap (write_decision_log.py)


def slugify(name: str) -> str:
    """Same lower-kebab rule as ``tools.grill_trace_fr_coverage.slugify`` (a test pins the parity). Not imported: that package binds
    the shared ``lib`` when it loads, which an in-process caller (a test, another script) may already own (ADR-045)."""
    return _SLUG_COLLAPSE_RE.sub("-", name.strip().lower()).strip("-")


def _load(path: Path, name: str):
    """A module by file path under a private name, registered before exec (ADR-045: never bind ``lib``)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def brief_sections(brief_md: str) -> dict[str, str]:
    """``{slug of the ## heading: section text}`` of brief.md."""
    marks = list(_SECTION_RE.finditer(brief_md))
    out: dict[str, str] = {}
    for i, m in enumerate(marks):
        slug = slugify(m.group(1))
        if not slug:
            continue
        body = brief_md[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(brief_md))]
        out[slug] = out[slug] + "\n" + _DUP_MARK + body if slug in out else body
    return out


def non_ui_verdict(section: str | None) -> tuple[bool, str]:
    """``(non_ui, why)``: the package says the capability has no screen only when its section states it."""
    if section is None:
        return False, "no section for it in brief.md"
    if _DUP_MARK in section:
        return False, "two brief.md headings map to the same capability name"
    if _UI_NONE_RE.search(section):  # an explicit "UI: none" wins over the bare word "screen" in prose; a concrete mockup reference still contradicts it
        if _MOCKUP_REF_RE.search(section):
            return False, "its brief.md section states UI: none but also names a mockup (the package contradicts itself)"
        return True, "its brief.md section states UI: none"
    if _SCREEN_REF_RE.search(section):  # a screen reference no screen-map entry covers is a contradiction
        return False, "its brief.md section refers to a mockup or screen that no screen-map entry covers (the package contradicts itself)"
    return False, "its brief.md section has no explicit `UI: none` line"


def _manifest_with(manifest: str, lines: list[str]) -> str:
    kept = [ln for ln in manifest.splitlines() if not (_PLACEHOLDER_RE.search(ln) and ln.lstrip().startswith("- FR-"))]
    text = "\n".join(kept) + "\n"
    m = re.search(r"^##\s+Non-UI FRs[^\n]*\n", text, re.M)
    block = "\n".join(lines) + "\n"
    if m:
        return text[:m.end()] + block + text[m.end():]
    nxt = re.search(r"^##\s+User Flows", text, re.M)
    section = "## Non-UI FRs\n\n" + block + "\n"
    return text[:nxt.start()] + section + text[nxt.start():] if nxt else text.rstrip("\n") + "\n\n" + section


def _log_decision(root: Path, frs: list[str]) -> str | None:
    shown = ", ".join(frs)
    names = shown if len(shown) < 300 else f"{len(frs)} FRs ({', '.join(frs[:8])}, ...)"
    proc = subprocess.run(
        [sys.executable, str(_SHARED / "scripts" / "tools" / "write_decision_log.py"), "--project-root", str(root),
         "--section", "Design (Brief package, non-UI FRs)", "--commit", "n/a",
         "--title", "Brief capabilities without a screen are non-UI FRs",
         "--context", f"The screen-map maps no screen to {names}; fr-coverage stays red until they are dealt with."[:_MAX],
         "--decision", ("Autonomous rule: the brief.md section of each of these capabilities states `UI: none` on a line of its own, "
                        "so they are recorded under ## Non-UI FRs in design-manifest.md; no screen is invented.")[:_MAX],
         "--consequences", "fr-coverage is satisfied; the FRs are verified by tests and checks, not by design-fidelity screenshots."[:_MAX],
         "--rejected", "Asking the person (the package already says so); re-approving the package; inventing screens."[:_MAX]],
        capture_output=True, text=True, encoding="utf-8")
    m = re.search(r"ADR-\d+", proc.stdout)
    return m.group(0) if proc.returncode == 0 and m else None


def run(root: Path) -> tuple[dict, int]:
    plan_check = _load(_SHARED / "scripts" / "lib" / "plan_design_check.py", "_shipwright_design_plan_design_check")
    if not plan_check.is_autonomous_design_run(root):
        return {"autonomous": False, "action": "ask", "recorded": [], "ask": [], "adr": None}, 0
    designs = root / ".shipwright" / "designs"
    manifest_path = designs / "design-manifest.md"
    if not (designs / "brief-package-applied.json").is_file() or not manifest_path.is_file():
        return {"error": "apply-brief-package.py and the design manifest (Step 6) must have run first"}, 2
    try:
        applied = _load(_HERE / "apply-brief-package.py", "_shipwright_design_apply_brief_package").apply(root)
    except Exception as exc:  # noqa: BLE001 - BriefRefused (unapproved/changed package) must stop with its message, never a traceback
        return {"error": f"{type(exc).__name__}: {exc}"}, 2
    if not applied.get("ok") or not applied.get("already_applied"):
        return {"error": "the package is not cleanly applied", "issues": applied.get("issues", [])}, 2
    manifest = manifest_path.read_text(encoding="utf-8")
    bdi = _load(_SHARED / "scripts" / "lib" / "brief_dir_intake.py", "_shipwright_design_brief_dir_intake")
    try:
        bdir, _ = bdi.recorded_dir(applied.get("brief_dir") or bdi.verify_run_config(root)["brief_dir"], root)
        sections = brief_sections((bdir / "brief.md").read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception as exc:  # noqa: BLE001 - a missing brief dir / brief.md is exit 2 with a message, never a traceback
        return {"error": f"the brief package's brief.md cannot be read ({type(exc).__name__})"}, 2
    fr_slug = {fr: slug for slug, ids in _load(_SHARED / "scripts" / "tools" / "brief_design_plan.py",
                                               "_shipwright_design_brief_design_plan").fr_ids_by_slug(root).items() for fr in ids}
    block = re.search(r"##\s+Non-UI FRs[^\n]*\n(.*?)(?=\n##\s+|\Z)", manifest, re.S)  # counts only here AND with an ADR (what fr-coverage honours)
    listed = {m.group(1) for ln in (block.group(1).splitlines() if block else []) if re.search(r"\bADR-\d+\b", ln)
              and (m := re.match(r"^-\s*(FR-[\d.]+)", ln.strip()))}
    recorded, ask = [], []
    for fr in applied["unmapped_frs"]:
        if fr in listed:
            continue
        non_ui, why = non_ui_verdict(sections.get(fr_slug[fr]) if fr_slug.get(fr) else None)
        (recorded if non_ui else ask).append({"fr": fr, "slug": fr_slug.get(fr), "why": why})
    adr = None
    if recorded:
        adr = _log_decision(root, [r["fr"] for r in recorded])
        if adr is None:
            return {"error": "the decision-log entry could not be written", "recorded": [], "ask": ask}, 2
        manifest_path.write_text(_manifest_with(manifest, [
            f"- {r['fr']} — {adr} (no screen: {r['why']})" for r in recorded]), encoding="utf-8")
    return {"autonomous": True, "action": "recorded" if recorded else ("ask" if ask else "nothing"),
            "recorded": recorded, "ask": ask, "adr": adr}, 1 if ask else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Record brief-declared non-UI FRs in an autonomous run")
    ap.add_argument("--project-root", required=True)
    out, code = run(Path(ap.parse_args().project_root).resolve())
    print(json.dumps(out, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
