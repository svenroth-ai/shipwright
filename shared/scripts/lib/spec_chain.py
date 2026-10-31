"""The spec chain: acceptance criterion (AC) -> run (event) -> plan -> pull request.

A requirement's history is only readable when each hop can be found without
guessing. This module is the single place that knows the hops:

* **Plan path.** Going forward one convention: ``.shipwright/planning/iterate/<run_id>/plan.md``,
  recorded on the ``work_completed`` event as ``plan_path``. Older runs are found by the
  fallbacks in :func:`find_plan` (the five shapes seen in the measurement), so a lookup
  also answers for runs recorded before the field existed.
* **Plan stub.** Three lines (goal = WHAT, reason = WHY, reference); a tiny run needs one line;
  a run that changes an AC or declares ``catalog_gap`` gets the full stub (three lines plus
  the affected ACs / the gap's FR). :func:`render_stub` writes them, :func:`parse_stub` reads
  them back (structure only - whether the sentences are true is a reviewer's question).
* **Pull request.** ``pr`` on the event when known; else the squash commit that carries the
  run id (``Run-ID:`` trailer), whose subject ends in ``(#123)``.
* **AC history.** ``affected_acs`` on events (P1) plus the run ids that the catalog's
  ``spec.md`` carries in the text of an AC (the backfill for runs before P1).

Everything is read-only, stdlib only and never raises on a missing file.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

__all__ = [
    "PLAN_NAME", "plan_rel_path", "safe_plan_path", "stub_kind", "render_stub", "parse_stub", "fold_plan_path",
    "find_plan", "find_pr", "parse_spec_acs", "ac_history", "normalise_ac", "load_events", "fr_history",
]

PLAN_NAME = "plan.md"
_ITERATE_DIR = ".shipwright/planning/iterate"
_ADR_DIR = ".shipwright/planning/adr"
_RUN_ID = re.compile(r"iterate-\d{4}-\d{2}-\d{2}-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")
_FR_HEADING = re.compile(r"^###\s+(FR-\d+\.\d+)\b")
_AC_START = re.compile(r"^-\s+(?:\([A-Z]\)\s+)?\[(AC\d+)\]")
_AC_ID = re.compile(r"^(FR-\d+\.\d+)[.\s_-]*(?:AC|ac)[-_ ]?(\d+)$")
_SAFE_RID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_PR_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")
_PLAN_NAMES_IN_RUN_DIR = ("plan.md", "mini-plan.md", "miniplan.md", "mini_plan.md", "MINIPLAN.md", "spec.md")


def plan_rel_path(run_id: str) -> str:
    """The one filename convention: ``.shipwright/planning/iterate/<run_id>/plan.md``."""
    return f"{_ITERATE_DIR}/{run_id}/{PLAN_NAME}"


def normalise_ac(raw: object) -> str | None:
    """``FR-01.03.AC05`` / ``FR-01.03 AC5`` -> ``FR-01.03.AC05``; ``None`` if not an AC id."""
    if not isinstance(raw, str):
        return None
    m = _AC_ID.match(raw.strip())
    return f"{m.group(1)}.AC{int(m.group(2)):02d}" if m else None


# --- plan stubs ---------------------------------------------------------------------------------

def stub_kind(acs: Iterable[object] = (), gap_fr: str = "", tiny: bool = False) -> str:
    """``full`` when the run changes an AC or declares a catalog gap, else ``tiny`` / ``three``."""
    if gap_fr or any(acs):
        return "full"
    return "tiny" if tiny else "three"


def render_stub(kind: str, goal: str, reason: str, ref: str, acs: Iterable[str] = (), gap_fr: str = "") -> str:
    """The stub text. ``tiny`` is one line; ``three``/``full`` start with the same three lines."""
    goal, reason, ref = (" ".join((s or "").split()) for s in (goal, reason, ref))
    if kind == "tiny":
        return f"Goal: {goal} | Reason: {reason} | Reference: {ref}\n"
    lines = [f"Goal: {goal}", f"Reason: {reason}", f"Reference: {ref}"]
    if kind == "full":
        listed = ", ".join(a for a in acs if a)
        if listed:
            lines.append(f"Affected ACs: {listed}")
        if gap_fr:
            lines.append(f"Catalog gap: {gap_fr}")
    return "\n".join(lines) + "\n"


def parse_stub(text: str) -> dict:
    """``{"goal", "reason", "reference"}`` as found (empty string when absent); structure only."""
    out = {"goal": "", "reason": "", "reference": ""}
    for part in re.split(r"\n|\s\|\s(?=(?:Goal|Reason|Reference):)", text or ""):
        m = re.match(r"\s*(Goal|Reason|Reference)(?:\s*\([^)]*\))?:\s*(.*)$", part)
        if m and not out[m.group(1).lower()]:
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def fold_plan_path(event: dict, project_root: Path, run_id: str) -> None:
    """Stamp ``plan_path`` on the event when the run wrote its plan stub and the caller did not name one."""
    if event.get("plan_path") or not run_id:
        return
    if (Path(project_root) / plan_rel_path(run_id)).is_file():
        event["plan_path"] = plan_rel_path(run_id)


# --- hop finders --------------------------------------------------------------------------------

def safe_plan_path(value: object) -> bool:
    """A recorded ``plan_path`` is read only when repo-relative and under ``.shipwright/planning/``."""
    if not isinstance(value, str) or not value:
        return False
    norm = value.replace("\\", "/")
    return norm.startswith(".shipwright/planning/") and ".." not in norm.split("/")


def find_plan(project_root: Path, event: dict) -> tuple[str, str] | None:
    """``(path, kind)`` of the run's plan, or ``None``. ``kind`` is ``field`` / ``convention`` / ``legacy`` / ``adr``."""
    root = Path(project_root)
    rid = str(event.get("adr_id") or "")
    recorded = event.get("plan_path")
    if safe_plan_path(recorded) and (root / recorded).is_file():
        return recorded.replace("\\", "/"), "field"
    if not rid or not _SAFE_RID.fullmatch(rid) or ".." in rid:
        return None
    base = root / _ITERATE_DIR
    run_dir = base / rid
    for name in _PLAN_NAMES_IN_RUN_DIR:
        if (run_dir / name).is_file():
            return f"{_ITERATE_DIR}/{rid}/{name}", "convention" if name == PLAN_NAME else "legacy"
    short = rid[len("iterate-"):] if rid.startswith("iterate-") else rid
    try:
        for stem in (rid, short):
            # exact name, or the stem plus a mini-plan suffix: never a bare prefix (run "x-p3" is not run "x-p3-spec-chain")
            pat = re.compile(re.escape(stem) + r"(-mini-?_?plan)?\.md", re.IGNORECASE)
            hits = sorted(p.name for p in base.iterdir() if p.is_file() and pat.fullmatch(p.name)) if base.is_dir() else []
            if hits:
                return f"{_ITERATE_DIR}/{hits[0]}", "legacy"
    except OSError:
        pass
    if (root / _ADR_DIR / f"{rid}.md").is_file():
        return f"{_ADR_DIR}/{rid}.md", "adr"
    return None


def find_pr(project_root: Path, event: dict, timeout: int = 60) -> tuple[int, str] | None:
    """``(pr_number, source)`` - ``field`` from the event, else ``git`` (a commit carrying the run id)."""
    pr = event.get("pr")
    if isinstance(pr, int) and not isinstance(pr, bool) and pr > 0:
        return pr, "field"
    if isinstance(pr, str) and pr.strip().lstrip("#").isdigit() and int(pr.strip().lstrip("#")) > 0:
        return int(pr.strip().lstrip("#")), "field"
    rid = str(event.get("adr_id") or "")
    if not rid or not _SAFE_RID.fullmatch(rid):
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "log", "--all", "--fixed-strings", f"--grep={rid}",
             "--format=%s%x1f%b%x1e"], capture_output=True, text=True, timeout=timeout, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    token = re.escape(rid) + r"(?![\w-])"
    trailer = re.compile(r"^Run-ID:\s*" + token, re.MULTILINE)
    mention = re.compile(r"(?<![\w-])" + token)
    fallback = None
    for rec in out.split("\x1e"):
        subject, _, body = rec.strip().partition("\x1f")
        m = _PR_SUBJECT.search(subject.strip())
        if not m:
            continue
        if trailer.search(body):
            return int(m.group(1)), "git"  # the Run-ID trailer is the stamp; a bare mention may be another PR's prose
        if fallback is None and mention.search(subject + "\n" + body):
            fallback = int(m.group(1))
    return (fallback, "git-mention") if fallback else None


# --- AC history ---------------------------------------------------------------------------------

def parse_spec_acs(spec_text: str) -> dict[str, list[str]]:
    """``{"FR-01.03.AC05": [run ids named in that AC's text], ...}`` for every AC in a ``spec.md``."""
    result: dict[str, list[str]] = {}
    fr, current, buf = "", "", []

    def flush() -> None:
        if current:
            runs = list(dict.fromkeys(_RUN_ID.findall(" ".join(buf))))
            result[current] = runs

    for line in (spec_text or "").splitlines():
        h = _FR_HEADING.match(line)
        start = _AC_START.match(line) if fr or h else None
        if h or start or line.startswith("#"):
            flush()
            current, buf = "", []
        if line.startswith("## ") and not h:
            fr = ""
        if h:
            fr = h.group(1)
        elif start and fr:
            current = f"{fr}.AC{int(start.group(1)[2:]):02d}"
            buf = [line]
        elif current and line.startswith(" "):
            buf.append(line)
        elif current and not line.strip():
            continue
        elif current:
            flush()
            current, buf = "", []
    flush()
    return result


def _event_acs(event: dict) -> list[tuple[str, str]]:
    out = []
    acs = event.get("affected_acs")
    if isinstance(acs, list):
        for item in acs:
            ac = normalise_ac(item.get("ac") if isinstance(item, dict) else item)
            if ac:
                out.append((ac, str(item.get("disposition") or "") if isinstance(item, dict) else ""))
    return out


def ac_history(project_root: Path, ac: str, events: list[dict], spec_acs: dict[str, list[str]] | None = None,
               with_pr: bool = True) -> dict:
    """Which runs shaped ``ac`` and, per run, its plan and PR. ``spec_acs`` defaults to the catalog's ``spec.md`` files."""
    root = Path(project_root)
    norm = normalise_ac(ac) or ac
    if spec_acs is None:
        spec_acs = {}
        for spec in sorted((root / ".shipwright" / "planning").glob("*/spec.md")):
            try:
                spec_acs.update(parse_spec_acs(spec.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    # by_run keeps the LAST work_completed event per run (later events overwrite earlier ones with the same adr_id).
    by_run = {str(e.get("adr_id")): e for e in events if e.get("type") == "work_completed" and e.get("adr_id")}
    runs: dict[str, dict] = {r: {"run_id": r, "via": ["spec-text"]} for r in spec_acs.get(norm, [])}
    for evt in events:
        if evt.get("type") != "work_completed" or not evt.get("adr_id"):
            continue
        for found, disposition in _event_acs(evt):
            if found == norm:
                entry = runs.setdefault(str(evt["adr_id"]), {"run_id": str(evt["adr_id"]), "via": []})
                entry["via"].append("event")
                entry["disposition"] = disposition
    rows = []
    for rid, entry in runs.items():
        evt = by_run.get(rid, {"adr_id": rid})
        plan = find_plan(root, evt)
        pr = find_pr(root, evt) if with_pr else None
        rows.append({**entry, "ts": evt.get("ts"), "event_found": rid in by_run,
                     "plan": plan[0] if plan else None, "plan_kind": plan[1] if plan else None,
                     "pr": pr[0] if pr else None})
    rows.sort(key=lambda r: str(r.get("ts") or ""))
    return {"ac": norm, "runs": rows}


def fr_history(project_root: Path, fr: str, events: list[dict], with_pr: bool = True) -> dict:
    """Runs that named ``fr`` in ``affected_frs`` (FR level), each with its plan and PR, plus the ACs of that FR with AC-level history."""
    root = Path(project_root)
    rows = []
    for evt in events:
        if evt.get("type") == "work_completed" and evt.get("adr_id") and fr in (evt.get("affected_frs") or []):
            plan = find_plan(root, evt)
            pr = find_pr(root, evt) if with_pr else None
            rows.append({"run_id": str(evt["adr_id"]), "ts": evt.get("ts"), "plan": plan[0] if plan else None,
                         "pr": pr[0] if pr else None})
    return {"fr": fr, "runs": rows}


def load_events(project_root: Path) -> list[dict]:
    """Every event in the project's log with ``event_amended`` corrections applied (bad lines skipped)."""
    from lib.events_log import resolve_events_path

    path = resolve_events_path(project_root)
    out: list[dict] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    from lib.events_amend import apply_amendments  # a `pr` added later via event_amended lands on its event
    return apply_amendments(out)
