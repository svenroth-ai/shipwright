#!/usr/bin/env python3
"""Project brief mode: satisfy /shipwright-project's gates BY CONTENT from a Brief package.

BRIEF D3. The grill-trace gate checks shape only, so this tool checks content in code:
every ``##`` section of ``brief.md`` (except ``## Glossary``) is one CAPABILITY; its
heading is the FR ``Name`` verbatim and its slug the ``requirement_key``.

Section format (one labelled line per field; ``n/a: <reason>`` is allowed, ``assumed`` is not)::

    ## Capture note
    Requirement: A user can add a note with a title and a body.
    - Outcome: ...            - Fit criterion: ...   (required when the outcome is answered)
    - Purpose: ...  - Boundaries: ...  - Failure: ...  - Rationale: ...  - Out of scope: ...
    - Glossary: ...           (optional when a ``## Glossary`` term appears in the section)

``apply`` verifies the package (hash + approval, ``brief_dir_intake``), checks that every
section and every dimension text is non-empty, and ONLY THEN writes the transcript
pointer, ``requirements.md``, one grill-trace per capability (``evidence:
["brief.md#<slug>"]``, ``confirmed_by: "brief:<path>"``) and the glossary terms
(``CONTEXT.md``). ``verify-traces`` re-checks that every brief-confirmed trace's evidence
anchor resolves to a non-empty section; ``check`` runs the content check alone (package intake calls it); ``check-fr-names`` checks spec.md FR Names equal
the brief's Names. Exit 0 ok, 1 content issues, 3 package refused.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import brief_dir_intake as bdi  # noqa: E402
from lib.file_lock import file_lock  # noqa: E402

from tools.grill_trace_format import DIMENSIONS, GrillTraceError, parse_trace, read_trace_dir  # noqa: E402
from tools.grill_trace_fr_coverage import extract_fr_names, slugify  # noqa: E402
from tools.write_context_term import upsert_term  # noqa: E402
from tools.verifiers.brief_mode_checks import (  # noqa: E402
    GLOSSARY_HEADING, anchor_issues, headed_sections, section_bodies,
)
from tools.write_grill_trace import write_trace  # noqa: E402

_LABEL_RE = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?([A-Za-z][A-Za-z ]*?)(?::\*\*|\*\*:|:)\s*(.*?)\s*$")
_TERM_RE = re.compile(r"^\s*[-*]\s+\*\*(.+?)(?:\*\*\s*[:–—-]|:\*\*|\*\*:)\s*(.+?)\s*$")  # **Term**: d, **Term:** d, **Term** - d
_LABELS = {d.replace("_", " "): d for d in DIMENSIONS} | {"fit criterion": "fit_criterion", "requirement": "requirement"}
PLANNING = Path(".shipwright/planning")


def parse_brief_md(text: str) -> tuple[list[dict], dict[str, str]]:
    """``(capabilities, glossary)``: capability = ``{name, key, body, labels, prose}``."""
    caps, glossary = [], {}
    for name, lines in headed_sections(text):
        if name.strip().lower() == GLOSSARY_HEADING:
            for line in lines:
                t = _TERM_RE.match(line)
                if t:
                    glossary[t.group(1).strip()] = t.group(2)
            continue
        labels, prose, dupes = {}, [], []
        for line in lines:
            m = _LABEL_RE.match(line)
            if m and m.group(1).strip().lower() in _LABELS:
                label = _LABELS[m.group(1).strip().lower()]
                dupes.append(label) if label in labels else labels.setdefault(label, m.group(2))
            elif line.strip():
                prose.append(line.strip())
        caps.append({"name": name, "key": slugify(name), "body": "\n".join(lines).strip(),
                     "labels": labels, "prose": prose, "dupes": dupes})
    return caps, glossary


def glossary_unparsed(text: str) -> list[str]:
    """Non-blank ``## Glossary`` lines that are not a term definition (a silent loss otherwise)."""
    return [ln.strip() for name, lines in headed_sections(text) if name.strip().lower() == GLOSSARY_HEADING
            for ln in lines if ln.strip() and not _TERM_RE.match(ln)]


def _uses(term: str, body: str) -> bool:
    """Exact-case, whole-word use of a glossary term ('ID' is not in 'Identity')."""
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", body) is not None


def check_capabilities(caps: list[dict], glossary: dict[str, str]) -> list[dict]:
    """Content issues (empty list = brief mode may write). Never judges prose quality."""
    issues: list[dict] = []
    seen: set[str] = set()
    if not caps:
        issues.append({"code": "no_capabilities", "capability": "", "message": "brief.md has no ## capability section"})
    for cap in caps:
        key, labels = cap["key"], cap["labels"]

        def bad(code: str, msg: str) -> None:
            issues.append({"code": code, "capability": cap["name"], "message": msg})

        if not key or key in seen:
            bad("bad_key", f"heading {cap['name']!r} gives an empty or duplicate requirement_key {key!r}")
        seen.add(key)
        for label in cap["dupes"]:
            bad("duplicate_label", f"'{label}' appears twice in the section")
        if not cap["body"]:
            bad("empty_section", "the section is empty, so brief.md#" + key + " resolves to nothing")
            continue
        if not (labels.get("requirement") or (cap["prose"][0] if cap["prose"] else "")):
            bad("no_requirement", "no 'Requirement:' line and no prose to use as the requirement text")
        has_term = any(_uses(t, cap["body"]) for t in glossary)
        for dim in DIMENSIONS:
            val = labels.get(dim, "").strip()
            if not val and dim == "glossary" and has_term:
                continue
            if not val:
                bad("empty_dimension", f"dimension '{dim}' has no text")
            elif val.lower().startswith("assumed"):
                bad("assumed_not_allowed", f"dimension '{dim}' is assumed; the project surface permits none")
            elif val.lower().startswith("n/a") and not val.partition(":")[2].strip():
                bad("empty_dimension", f"dimension '{dim}' is n/a without a reason (the form is 'n/a: <reason>')")
        if labels.get("outcome") and not labels["outcome"].lower().startswith("n/a") and not labels.get("fit_criterion", "").strip():
            bad("no_fit_criterion", "the outcome is answered but 'Fit criterion:' is empty")
    return issues


def _dimension(cap: dict, dim: str) -> str:
    val = cap["labels"].get(dim, "").strip()
    if not val:
        return "answered"  # only reachable for glossary, covered by a glossary term
    return "n/a:" + val.partition(":")[2].strip() if val.lower().startswith("n/a") else "answered"


def build_trace(cap: dict, glossary: dict[str, str], brief_path: str) -> dict:
    terms = [t for t in glossary if _uses(t, cap["body"])]
    outcome_ok = _dimension(cap, "outcome") == "answered"
    return {
        "requirement_key": cap["key"],
        "requirement_text": cap["labels"].get("requirement") or cap["prose"][0],
        "surface": "project", "evidence": [f"brief.md#{cap['key']}"],
        "dimensions": {d: _dimension(cap, d) for d in DIMENSIONS},
        "fit_criterion": cap["labels"]["fit_criterion"] if outcome_ok else None,
        "glossary_delta": [{"term": t, "recorded_in": "CONTEXT.md"} for t in terms],
        "confirmed_by": f"brief:{brief_path}", "terms_used": terms,
    }


def _open(root: Path, brief_dir: str | None) -> tuple[Path, str, dict, str]:
    """``(dir, rel, verified info, brief.md text)``. run_config's recorded hash is the only
    baseline once a ``brief_dir`` is recorded; ``--brief-dir`` is for the first use. The text
    is read BEFORE the verification (narrows the swap window; a verified snapshot is deferred to U3)."""
    cfg = bdi.load_config(root)
    if "brief_dir" not in cfg and "brief_package" in cfg:
        raise bdi.BriefRefused("missing_record", "run_config holds a brief_package but no brief_dir: restore the original run_config")
    if "brief_dir" in cfg:
        bdir, _rel = bdi.recorded_dir(cfg["brief_dir"], root)
        if brief_dir and bdi.resolve_dir(brief_dir, root) != bdir:
            raise bdi.BriefRefused("brief_dir_conflict", f"--brief-dir differs from the recorded {cfg['brief_dir']!r}")
        recorded = cfg.get("brief_package") or {}
    elif brief_dir:
        bdir, recorded = bdi.resolve_dir(brief_dir, root), None
    else:
        raise bdi.BriefRefused("no_brief_dir", "run_config records no brief_dir; pass --brief-dir")
    rel = bdi._relative(bdir, root)
    text = bdi.read_text(bdir / "brief.md")
    info = bdi.open_package(bdir, recorded=recorded)
    bdi.check_brief_dir(info["brief"], rel)
    bdi.check_config_matches(cfg, info["brief"])
    return bdir, rel, info, text


def content_issues(text: str) -> tuple[list[dict], dict[str, str], list[dict]]:
    """``(caps, glossary, issues)``: the one content check, shared by ``apply`` and ``check``."""
    caps, glossary = parse_brief_md(text)
    issues = check_capabilities(caps, glossary) + [
        {"code": "glossary_line_unparsed", "capability": "",
         "message": f"## Glossary line is not '- **Term**: definition': {line!r}"} for line in glossary_unparsed(text)]
    return caps, glossary, issues


def check(root: Path, brief_dir: str | None = None) -> dict:
    """The content check alone (what package intake runs after it verified the package itself): reads ``brief.md``, writes nothing."""
    issues = content_issues(bdi.read_text(bdi.resolve_dir(brief_dir or ".", root) / "brief.md"))[2]
    return {"ok": not issues, "issues": issues}


def apply(root: Path, brief_dir: str | None = None) -> dict:
    bdir, rel, info, text = _open(root, brief_dir)
    caps, glossary, issues = content_issues(text)
    traces = [] if issues else [build_trace(c, glossary, f"{rel}/brief.md") for c in caps]
    for cap, trace in zip(caps, traces):  # validate EVERY trace before the first write
        try:
            parse_trace(trace)
        except GrillTraceError as exc:
            issues.append({"code": "invalid_trace", "capability": cap["name"], "message": str(exc)})
    if issues:
        return {"ok": False, "issues": issues}
    planning = root / PLANNING
    planning.mkdir(parents=True, exist_ok=True)
    sha = info["package_sha256"]
    write = bdi._lib("atomic_write").durable_atomic_write
    write(planning / "shipwright_project_interview.md",
        f"# Interview transcript\n\nProject brief mode: no interview was held. Source: `{rel}/brief.md` "
        f"(package sha256 `{sha}`, approved by `{info['approved_by']}`).\n\nCapabilities: "
        + ", ".join(c["name"] for c in caps) + "\n")
    write(planning / "requirements.md",
        "# Requirements\n\nSource: " + f"`{rel}/brief.md`\n\n" + "".join(
            f"## {c['name']}\n\n{c['labels'].get('requirement') or c['prose'][0]}\n\n" for c in caps))
    context = root / "CONTEXT.md"
    for term, definition in glossary.items():
        with file_lock(context.with_suffix(".md.lock"), timeout_seconds=5.0):
            upsert_term(context, term=term, definition=definition)
    for trace in traces:
        write_trace(planning, trace, lock_timeout=5.0)
    return {"ok": True, "capabilities": [c["key"] for c in caps], "glossary_terms": sorted(glossary),
            "package_sha256": sha}


def verify_traces(root: Path, brief_dir: str | None = None) -> dict:
    """Every brief-confirmed trace's evidence anchor must resolve to a non-empty section (the same
    check ``run_project_checks`` runs through ``verifiers/brief_mode_checks.py``)."""
    _bdir, rel, _info, text = _open(root, brief_dir)
    issues = anchor_issues(read_trace_dir(root / PLANNING), section_bodies(text), rel)
    return {"ok": not issues, "issues": issues}


def check_fr_names(root: Path, brief_dir: str | None = None) -> dict:
    """spec.md FR Names must equal the brief's capability Names (verbatim, as sets)."""
    _bdir, _rel, _info, text = _open(root, brief_dir)
    caps, _g = parse_brief_md(text)
    brief_names = {c["name"] for c in caps}
    fr_names: set[str] = set()
    for spec in sorted((root / PLANNING).glob("*/spec.md")):
        fr_names |= set(extract_fr_names(spec.read_text(encoding="utf-8", errors="ignore")).values())
    missing, extra = sorted(brief_names - fr_names), sorted(fr_names - brief_names)
    return {"ok": not (missing or extra), "missing_in_specs": missing, "not_in_brief": extra}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["apply", "check", "verify-traces", "check-fr-names"])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--brief-dir", default=None)
    args = parser.parse_args(argv)
    fn = {"apply": apply, "check": check, "verify-traces": verify_traces, "check-fr-names": check_fr_names}[args.command]
    try:
        out = fn(Path(args.project_root).resolve(), args.brief_dir)
    except bdi.BriefRefused as exc:
        print(json.dumps(exc.as_dict(), indent=2))
        return 3
    except (OSError, ValueError, RuntimeError) as exc:  # LockTimeout (RuntimeError), rejected payload: structured error
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
