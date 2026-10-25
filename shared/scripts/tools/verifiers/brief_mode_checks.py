"""Project brief mode checks, registered in ``project_checks.run_project_checks`` (campaign
brief-driven-run, B2; BRIEF D3). They apply ONLY to a run whose ``shipwright_run_config.json``
records a ``brief_dir`` -- every other project gets no result from here.

The grill-trace gate checks shape only; these two read the brief's CONTENT:

* ``brief_evidence_anchors`` -- every trace confirmed by the brief
  (``confirmed_by: "brief:<dir>/brief.md"``) must carry only ``brief.md#<slug>`` anchors, each
  resolving to a non-empty ``##`` section of the recorded ``brief.md``;
* ``brief_fr_names`` -- the live FR ``Name`` cells in the split specs equal the brief's capability
  headings verbatim (skipped until a spec.md exists).

No ``lib`` import of its own (this runs inside the run plugin's validators, ADR-045; ``.common`` already carries one);
``tools/brief_project_mode.py`` reuses :func:`section_bodies` and :func:`anchor_issues`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .common import CheckResult, Severity, read_run_config

if TYPE_CHECKING:  # the tools.* helpers load lazily: project_checks imports this module for EVERY project gate
    from tools.grill_trace_format import GrillTrace

PLANNING = Path(".shipwright/planning")
GLOSSARY_HEADING = "glossary"
_HEADING_RE = re.compile(r"^##\s+(.+?)(?:\s+#+)?\s*$")  # CommonMark: only a SPACED trailing # run closes the heading
_FENCE_LINE_RE = re.compile(r"^\s*(```|~~~)")
_ANCHOR_RE = re.compile(r"brief\.md#([a-z0-9]+(?:-[a-z0-9]+)*)")


def headed_sections(text: str) -> list[tuple[str, list[str]]]:
    """``[(heading, body lines)]`` for every ``##`` section."""
    out: list[tuple[str, list[str]]] = []
    fenced = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if _FENCE_LINE_RE.match(line):
            fenced = not fenced
        m = None if fenced else _HEADING_RE.match(line)
        if m:
            out.append((m.group(1), []))
        elif out:
            out[-1][1].append(line)
    return out


def section_bodies(text: str) -> dict[str, str]:
    """``{slug: body}`` of the capability sections (``## Glossary`` is not one)."""
    from tools.grill_trace_fr_coverage import slugify

    return {slugify(name): "\n".join(lines).strip() for name, lines in headed_sections(text)
            if name.strip().lower() != GLOSSARY_HEADING}


def anchor_issues(traces: list[GrillTrace], sections: dict[str, str], rel: str) -> list[dict]:
    """Content issues of the brief-confirmed traces against the recorded ``brief.md``."""
    issues: list[dict] = []
    for trace in traces:
        key = trace.requirement_key

        def bad(code: str, message: str) -> None:
            issues.append({"code": code, "capability": key, "message": message})

        if trace.confirmed_by != f"brief:{rel}/brief.md":  # a brief run's traces all come from the brief
            bad("wrong_source", trace.confirmed_by)
        if not trace.evidence:
            bad("no_evidence", "empty evidence")
        for ev in trace.evidence:
            m = _ANCHOR_RE.fullmatch(ev)
            if not m:
                bad("evidence_not_anchored", ev)
            elif m.group(1) != key:
                bad("anchor_key_mismatch", f"{ev} is not the section of requirement_key {key!r}")
            elif not sections.get(m.group(1), "").strip():
                bad("anchor_empty", f"{ev} resolves to a missing or empty section")
    return issues


def _brief(project_root: Path) -> tuple[str, str] | None:
    cfg = read_run_config(project_root)
    brief_dir = cfg.get("brief_dir") if isinstance(cfg, dict) else None
    if not (isinstance(brief_dir, str) and brief_dir.strip()):
        return None
    rel = brief_dir.replace("\\", "/").strip("/")
    if Path(rel).is_absolute() or Path(brief_dir).is_absolute() or ".." in rel.split("/"):
        raise ValueError(f"recorded brief_dir {brief_dir!r} is not a project-relative path")
    return rel, brief_dir


def _brief_text(project_root: Path, rel: str) -> str | None:
    path = project_root / rel / "brief.md"
    try:
        if not path.resolve().is_relative_to(project_root.resolve()):  # a link must not lead out of the project
            return None
        return path.read_text(encoding="utf-8-sig")
    except (OSError, ValueError):
        return None


def _guarded(name: str, check, project_root: Path) -> list[CheckResult]:
    """A bug or unreadable input is a red result, never a crash of the whole gate."""
    try:
        return check(project_root)
    except Exception as exc:  # noqa: BLE001
        return [CheckResult(name, False, f"{name} raised {type(exc).__name__}: {exc}")]


def check_brief_evidence_anchors(project_root: Path) -> list[CheckResult]:
    return _guarded("brief_evidence_anchors", _anchors, project_root)


def check_brief_package(project_root: Path) -> list[CheckResult]:
    return _guarded("brief_package_hash", _package_hash, project_root)


def check_brief_fr_names(project_root: Path) -> list[CheckResult]:
    return _guarded("brief_fr_names", _fr_names, project_root)


_BDI = "_shipwright_brief_mode_checks_bdi"


def _package_hash(project_root: Path) -> list[CheckResult]:
    """The recorded package must still verify against the hash held in run_config."""
    if _brief(project_root) is None:
        return []
    import importlib.util
    import sys

    if _BDI not in sys.modules:  # by file path, registered before exec (ADR-045: no ``lib`` import)
        path = Path(__file__).resolve().parents[2] / "lib" / "brief_dir_intake.py"
        spec = importlib.util.spec_from_file_location(_BDI, path)
        sys.modules[_BDI] = module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(_BDI, None)
            raise
    try:
        out = sys.modules[_BDI].verify_run_config(project_root)
    except Exception as exc:  # noqa: BLE001 -- BriefRefused is a class per loader: duck-typed
        if not hasattr(exc, "as_dict"):
            raise
        return [CheckResult("brief_package_hash", False, f"{exc.code}: {exc.message}")]
    return [CheckResult("brief_package_hash", True, f"package verified (sha256 {out.get('package_sha256', '')[:12]}...)")]


def _anchors(project_root: Path) -> list[CheckResult]:
    found = _brief(project_root)
    if found is None:
        return []
    rel, _raw = found
    name = "brief_evidence_anchors"
    from tools.grill_trace_format import read_trace_dir

    text = _brief_text(project_root, rel)
    if text is None:
        return [CheckResult(name, False, f"{rel}/brief.md is missing or unreadable")]
    try:
        traces = read_trace_dir(project_root / PLANNING)
    except Exception as exc:  # noqa: BLE001 -- surface a broken trace, never crash the gate
        return [CheckResult(name, False, f"grill-traces unreadable: {type(exc).__name__}: {exc}")]
    sections = section_bodies(text)
    issues = anchor_issues(traces, sections, rel)
    have = {t.requirement_key for t in traces}
    issues += [{"code": "missing_trace", "capability": key, "message": f"no grill-trace for brief.md#{key}"}
               for key in sections if key not in have]
    if issues:
        return [CheckResult(name, False, "; ".join(f"{i['capability']}: {i['code']} ({i['message']})" for i in issues))]
    return [CheckResult(name, True, "every brief-confirmed trace anchors to a non-empty brief.md section")]


def _fr_names(project_root: Path) -> list[CheckResult]:
    found = _brief(project_root)
    if found is None:
        return []
    rel, _raw = found
    name = "brief_fr_names"
    from tools.grill_trace_fr_coverage import extract_fr_names

    specs = sorted((project_root / PLANNING).glob("*/spec.md"))
    fr_names: set[str] = set()
    for spec in specs:
        fr_names |= set(extract_fr_names(spec.read_text(encoding="utf-8", errors="ignore")).values())
    if not specs:
        return [CheckResult(name, None, "no spec.md yet -- nothing to compare", severity=Severity.SKIPPED.value)]
    text = _brief_text(project_root, rel)
    if text is None:
        return [CheckResult(name, False, f"{rel}/brief.md is missing or unreadable")]
    brief_names = {n for n, _ in headed_sections(text) if n.strip().lower() != GLOSSARY_HEADING}
    missing, extra = sorted(brief_names - fr_names), sorted(fr_names - brief_names)
    if missing or extra:
        return [CheckResult(name, False, f"brief Names without an FR: {missing}; FR Names not in the brief: {extra}")]
    return [CheckResult(name, True, f"{len(fr_names)} FR Name(s) equal the brief's capability Names")]
