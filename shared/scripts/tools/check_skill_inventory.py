#!/usr/bin/env python3
"""Check a skill's migration inventory against the skill as it stands (DFP programme P10).

Deterministic-first pilot, unit P0. The inventory is a migration tool: it lists every section of
``SKILL.md`` and of every reference file, gives each a class and a target, and is retired for a
plugin at its definition of done. This checker keeps it honest while the migration runs.
    uv run shared/scripts/tools/check_skill_inventory.py --skill-dir plugins/shipwright-changelog/skills/changelog \
        --data-dir .shipwright/planning/campaigns/2026-10-25-dfp-pilot-changelog-inventory [--repo-root .] [--json] [--refresh]

``--data-dir`` holds three data files (default: the skill directory); they live with the campaign reports, not in the plugin:
* ``inventory.json``      sections (anchor = file + heading path + content hash), class, target, runtime inputs
* ``truth_table.json``    every {context} x {autonomy} x {question} cell with the line or gate it comes from
* ``subprocess_map.json`` every binary, resolution, audit and network call on a scenario path, with its plan
Checks (every failure is one line; exit 1 when any):
1. every heading section of ``SKILL.md`` and ``references/*.md`` is inventoried, no entry is orphaned,
   and no content hash is stale (a section with several instructions is ``mixed`` and lists ``parts``) (``--refresh`` rewrites hashes and adds new anchors as ``unclassified``);
2. every class and target is in the programme vocabulary; ``runtime-input`` goes with ``keep``, and
   every declared runtime input exists, is read by the named code, and is classified so;
3. the truth table has exactly one cell per context/autonomy/question, each cites sources that exist;
4. every subprocess-map entry cites a valid line range that still contains its needle, and has a valid plan.
Refresh procedure (a red here is a drift, not a bug): either revert the prose edit, or re-pin: run with
``--refresh`` (rewrites every content hash, adds new sections as ``unclassified``), give each new section a class and
target, fix any cited line the tool names, re-check by hand the truth-table line citations (range-checked only) and the map's completeness (never checked), and commit the data files in the same diff as the prose. Owner: the pilot
campaign. A renumbered duplicate heading ("X #2") shows as an orphan plus a new section: move its class by hand.
Run by the pilot's own units only, through this CLI (not in CI, not in verify_local; the unit tests here never read the real skill) and retired at the pilot's P7.

Exit codes: 0 consistent; 1 inconsistent; 2 an input file is missing or unreadable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

CLASSES = {"judgement", "ask", "mechanic", "rationale", "method", "reference", "runtime-input", "unclassified"}
SECTION_CLASSES = CLASSES | {"mixed"}  # mixed: the section carries several instructions, each listed under "parts"
TARGET_RE = re.compile(r"^(keep|adr|delete|cli:[a-z][a-z-]*|pack:[a-z][a-z-]*)$")
PLANS = {"seam", "offline", "impossible", "none-needed"}
BEHAVIOURS = {"asks", "auto-accepts", "skips", "merges", "stays-open", "no-question", "not-applicable", "contradicted"}
CONTEXTS = ("standalone", "pipeline")
AUTONOMY = ("guided", "autonomous", "unattended")
QUESTIONS = ("out-of-sequence", "version", "legacy-bullets", "preview", "pr-merge")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*$")
_SOURCE = re.compile(r"^(?P<path>[^:]+?)(?::(?P<a>\d+)(?:-(?P<b>\d+))?)?$")


def _digest(lines: list[str]) -> str:
    text = "\n".join(line.rstrip() for line in lines).strip("\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def parse_sections(text: str) -> list[dict]:
    """Flat sections: a heading line runs until the next heading of any level (fenced lines are never headings)."""
    sections: list[dict] = []
    stack: list[tuple[int, str]] = []
    current: dict = {"path": "(preamble)", "lines": []}
    fence = None
    for raw in text.replace("\r\n", "\n").split("\n"):
        marker = _FENCE.match(raw)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and _FENCE_CLOSE.match(raw):
                fence = None
        heading = None if fence is not None or marker else _HEADING.match(raw)
        if heading:
            sections.append(current)
            level, title = len(heading.group(1)), heading.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current = {"path": " > ".join(t for _, t in stack), "lines": [raw]}
        else:
            current["lines"].append(raw)
    sections.append(current)
    seen: dict[str, int] = {}
    out = []
    for sec in sections:
        body = [line for line in sec["lines"] if line.strip()]
        if sec["path"] == "(preamble)" and not body:
            continue
        seen[sec["path"]] = seen.get(sec["path"], 0) + 1
        path = sec["path"] if seen[sec["path"]] == 1 else f"{sec['path']} #{seen[sec['path']]}"
        out.append({"path": path, "hash": _digest(sec["lines"])})
    return out


def live_anchors(skill_dir: Path) -> dict[tuple[str, str], str]:
    files = [skill_dir / "SKILL.md", *sorted((skill_dir / "references").glob("*.md"))]
    anchors: dict[tuple[str, str], str] = {}
    for f in files:
        if not f.is_file():
            print(f"check_skill_inventory: missing {f}", file=sys.stderr)
            raise SystemExit(2)
        rel = f.relative_to(skill_dir).as_posix()
        for sec in parse_sections(f.read_text(encoding="utf-8-sig")):
            anchors[(rel, sec["path"])] = sec["hash"]
    return anchors


def _class_target_errs(cls: str | None, target: str, where: str) -> list[str]:
    errs = []
    if not TARGET_RE.match(target or ""):
        errs.append(f"inventory: unknown target {target!r} at {where}")
    if cls == "runtime-input" and target != "keep":
        errs.append(f"inventory: runtime-input must be keep, got {target!r} at {where}")
    if cls == "mechanic" and target in ("delete", "adr"):
        errs.append(f"inventory: a mechanic cannot be {target!r} at {where}")
    return errs


def check_inventory(inv: dict, skill_dir: Path, repo_root: Path) -> list[str]:
    errs: list[str] = []
    live = live_anchors(skill_dir)
    listed: set[tuple[str, str]] = set()
    runtime_files = {r.get("file") for r in inv.get("runtime_inputs", [])}
    for i, e in enumerate(inv.get("sections", [])):
        if not e.get("file") or not e.get("path"):
            errs.append(f"inventory: entry #{i} lacks file or path")
            continue
        key = (e["file"], e["path"])
        if key in listed:
            errs.append(f"inventory: duplicate anchor {key[0]} :: {key[1]}")
        listed.add(key)
        if key not in live:
            errs.append(f"inventory: orphan entry (no such section) {key[0]} :: {key[1]}")
        elif live[key] != e.get("hash"):
            errs.append(f"inventory: stale hash {key[0]} :: {key[1]} (live {live[key]}, recorded {e.get('hash')})")
        cls, target = e.get("class"), e.get("target", "")
        where = f"{key[0]} :: {key[1]}"
        if cls == "unclassified":
            errs.append(f"inventory: unclassified {where}")
        elif cls not in SECTION_CLASSES:
            errs.append(f"inventory: unknown class {cls!r} at {where}")
        if (cls == "mixed") != bool(e.get("parts")):
            errs.append(f"inventory: class mixed and parts disagree at {where}")
        errs += _class_target_errs(cls, target, where)
        for part in e.get("parts", []):
            if part.get("class") not in CLASSES - {"unclassified"}:
                errs.append(f"inventory: bad part class {part.get('class')!r} ({part.get('what')!r}) at {where}")
            errs += _class_target_errs(part.get("class"), part.get("target", ""), f"{where} (part {part.get('what')!r})")
        if (cls == "runtime-input") != (e["file"] in runtime_files):
            errs.append(f"inventory: runtime-input class and runtime_inputs disagree for {e['file']}")
    for key in sorted(set(live) - listed):
        errs.append(f"inventory: section not inventoried {key[0]} :: {key[1]}")
    for r in inv.get("runtime_inputs", []):
        if not r.get("file") or not r.get("read_by"):
            errs.append("inventory: a runtime input lacks file or read_by")
            continue
        if not (skill_dir / r["file"]).is_file():
            errs.append(f"inventory: runtime input missing {r['file']}")
        reader = repo_root / r["read_by"]
        if not reader.is_file() or Path(r["file"]).name not in reader.read_text(encoding="utf-8"):
            errs.append(f"inventory: {r['read_by']} does not name the file name of runtime input {r['file']}")
    return errs


def _source_ok(src: str, repo_root: Path) -> str | None:
    m = _SOURCE.match(src)
    if not m:
        return f"unparsable source {src!r}"
    path = repo_root / m.group("path")
    if not path.is_file():
        return f"source file missing {src!r}"
    if m.group("a"):
        total = len(path.read_text(encoding="utf-8").splitlines())
        a, b = int(m.group("a")), int(m.group("b") or m.group("a"))
        if a < 1 or b < a:
            return f"source range invalid {src!r}"
        if b > total:
            return f"source line out of range {src!r} (file has {total})"
    return None


def check_truth_table(tt: dict, repo_root: Path) -> list[str]:
    errs: list[str] = []
    expected = {(c, a, q) for c in CONTEXTS for a in AUTONOMY for q in QUESTIONS}
    seen: set[tuple[str, str, str]] = set()
    for cell in tt.get("cells", []):
        key = (cell.get("context"), cell.get("autonomy"), cell.get("question"))
        if key in seen:
            errs.append(f"truth table: duplicate cell {key}")
        seen.add(key)
        if key not in expected:
            errs.append(f"truth table: unknown cell {key}")
        if cell.get("behaviour") not in BEHAVIOURS:
            errs.append(f"truth table: unknown behaviour {cell.get('behaviour')!r} at {key}")
        if not cell.get("source"):
            errs.append(f"truth table: cell {key} cites no source")
        sources = cell.get("source") or []
        if not isinstance(sources, list):
            errs.append(f"truth table: cell {key} source must be a list")
            continue
        for src in sources:
            msg = _source_ok(src, repo_root)
            if msg:
                errs.append(f"truth table: {key}: {msg}")
    for key in sorted(expected - seen):
        errs.append(f"truth table: missing cell {key}")
    return errs


def check_subprocess_map(sm: dict, repo_root: Path) -> list[str]:
    errs: list[str] = []
    for i, e in enumerate(sm.get("entries", [])):
        label = f"subprocess map #{i} {e.get('file')}:{e.get('line')}"
        if e.get("plan") not in PLANS:
            errs.append(f"{label}: unknown plan {e.get('plan')!r}")
        path = repo_root / e.get("file", "")
        if not path.is_file():
            errs.append(f"{label}: file missing")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        end = e.get("end", e.get("line"))
        if not (isinstance(e.get("line"), int) and isinstance(end, int) and 1 <= e["line"] <= end <= len(lines)) or not e.get("needle"):
            errs.append(f"{label}: needs a needle and an integer line range, 1 <= line <= end <= {len(lines)}")
            continue
        window = lines[e["line"] - 1: end]
        if not any(e["needle"] in line for line in window):
            errs.append(f"{label}: needle {e['needle']!r} not found (line moved?)")
    return errs


def refresh(inv_path: Path, inv: dict, skill_dir: Path) -> None:
    """Rewrite hashes, drop nothing silently: orphans stay (reported), new sections arrive unclassified."""
    live = live_anchors(skill_dir)
    inv.setdefault("sections", [])
    known = {(e["file"], e["path"]): e for e in inv["sections"] if e.get("file") and e.get("path")}
    for key, digest in live.items():
        entry = known.get(key)
        if entry:
            entry["hash"] = digest
        else:
            inv["sections"].append({"file": key[0], "path": key[1], "hash": digest, "class": "unclassified", "target": "keep"})
    write_inventory(inv_path, inv)


def write_inventory(path: Path, inv: dict) -> None:
    head = {k: v for k, v in inv.items() if k != "sections"}
    rows = ",\n".join("  " + json.dumps(s, ensure_ascii=False) for s in inv["sections"])
    body = json.dumps(head, ensure_ascii=False)[:-1]
    sep = ", " if head else ""
    path.write_text(f'{body}{sep}"sections": [\n{rows}\n]}}\n', encoding="utf-8", newline="\n")


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"check_skill_inventory: cannot read {path}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if not isinstance(data, dict):
        print(f"check_skill_inventory: {path} must hold a JSON object", file=sys.stderr)
        raise SystemExit(2)
    return data


def run(skill_dir: Path, repo_root: Path, do_refresh: bool = False, data_dir: Path | None = None) -> list[str]:
    data_dir = data_dir or skill_dir
    inv_path = data_dir / "inventory.json"
    inv = _load(inv_path)
    if do_refresh:
        refresh(inv_path, inv, skill_dir)
        inv = _load(inv_path)
    errs = check_inventory(inv, skill_dir, repo_root)
    errs += check_truth_table(_load(data_dir / "truth_table.json"), repo_root)
    errs += check_subprocess_map(_load(data_dir / "subprocess_map.json"), repo_root)
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--skill-dir", required=True)
    ap.add_argument("--data-dir", help="where the three data files live (default: --skill-dir)")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="rewrite hashes; new sections become unclassified")
    args = ap.parse_args(argv)
    errs = run(Path(args.skill_dir).resolve(), Path(args.repo_root).resolve(), args.refresh,
               Path(args.data_dir).resolve() if args.data_dir else None)
    if args.json:
        print(json.dumps({"ok": not errs, "errors": errs}, indent=2))
    else:
        for e in errs:
            print(e)
        print("skill inventory: ok" if not errs else
              f"skill inventory: {len(errs)} problem(s): re-pin (--refresh, then classify what is new) or revert the edit")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
