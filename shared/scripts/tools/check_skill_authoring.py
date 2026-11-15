#!/usr/bin/env python3
"""Check skills against the machine-readable authoring limits (docs/building-skills-plugins-agents.md).

The numbers live once, in ``shared/config/conventions.json`` (section ``skill_authoring``, ``limits``); this tool reads them
and reports every skill that breaks one. It is a report, not a gate: it is not in CI and not in
``verify_local``. Skills that predate a limit are listed, not blocked.

    uv run shared/scripts/tools/check_skill_authoring.py --all [--repo-root .] [--json] [--strict]
    uv run shared/scripts/tools/check_skill_authoring.py --skill-dir plugins/shipwright-changelog/skills/changelog

Findings carry the limit's own ``kind``: ``hard`` (a stated requirement) or ``recommended``.
Exit codes: 0 no hard finding (and, with ``--strict``, no finding at all); 1 findings; 2 a file is missing
or unreadable. Limits whose ``checkable`` is false (third person, the runtime caps) are never checked here.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

DEFAULT_RULES = Path(__file__).resolve().parents[2] / "config" / "conventions.json"
_LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")


def load_limits(rules_path: Path) -> dict[str, dict]:
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    return {item["id"]: item for item in data["sections"]["skill_authoring"]["limits"]}


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (fields, body). Only top-level ``key: value`` lines are read; a quoted value is JSON-decoded."""
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        return {}, text
    fields: dict[str, str] = {}
    key = None
    for raw in lines[1:end]:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", raw)
        if m:
            key = m.group(1)
            value = m.group(2).strip()
            fields[key] = "" if value in {">", "|", ">-", "|-"} else value  # a block scalar's text is the indented lines below
        elif key and raw.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + raw.strip()).strip()
    for k, v in list(fields.items()):
        if v[:1] == '"' and v[-1:] == '"' and len(v) >= 2:
            try:
                fields[k] = json.loads(v)
            except ValueError:
                fields[k] = v[1:-1]
        elif v[:1] == "'" and v[-1:] == "'" and len(v) >= 2:
            fields[k] = v[1:-1].replace("''", "'")  # YAML single quotes: '' is one quote
    return fields, "\n".join(lines[end + 1:])


def _finding(skill: str, file: str, limit: dict, message: str) -> dict:
    return {"skill": skill, "file": file, "limit": limit["id"], "kind": limit["kind"], "message": message}


def _frontmatter_findings(skill, file, fields, limits):
    out = []
    name, desc = fields.get("name", ""), fields.get("description", "")
    lim = limits["name-required"]
    if not name.strip():
        out.append(_finding(skill, file, lim, "name is missing or empty"))
    lim = limits["name-max-length"]
    if len(name) > lim["value"]:
        out.append(_finding(skill, file, lim, f"name is {len(name)} chars, limit {lim['value']}"))
    lim = limits["name-charset"]
    if name and not re.fullmatch(lim["value"], name):
        out.append(_finding(skill, file, lim, f"name {name!r} has characters outside lowercase letters, digits, hyphen"))
    lim = limits["name-reserved-words"]
    out += [_finding(skill, file, lim, f"name contains the reserved word {w!r}") for w in lim["value"] if w in name]
    lim = limits["description-required"]
    if not desc.strip():
        out.append(_finding(skill, file, lim, "description is missing or empty"))
    lim = limits["description-max-length"]
    if len(desc) > lim["value"]:
        out.append(_finding(skill, file, lim, f"description is {len(desc)} chars, limit {lim['value']}"))
    lim = limits["no-xml-tags"]
    for label, value in (("name", name), ("description", desc)):
        if re.search(lim["value"], value):
            out.append(_finding(skill, file, lim, f"{label} contains an XML-like tag"))
    return out


def _reference_targets(text: str, base: str, ref_names: set[str]) -> set[str]:
    """Names of this skill's reference files that ``text`` links or names by path.

    ``base`` is the directory of the file the text belongs to, relative to the skill ('' for SKILL.md,
    'references' for a reference file), so a link is resolved, not matched by file name alone.
    """
    found = set()
    for m in _LINK.findall(text):
        if m.startswith(("http:", "https:")):
            continue
        resolved = posixpath.normpath(posixpath.join(base, m))
        if posixpath.dirname(resolved) == "references" and posixpath.basename(resolved) in ref_names:
            found.add(posixpath.basename(resolved))
    # a plain mention such as `references/a.md`; a path that continues to the left (../other/references/a.md) is another file
    return found | {n for n in ref_names if re.search(rf"(?<![\w./-]){re.escape('references/' + n)}", text)}


def check_skill(skill_dir: Path, limits: dict[str, dict]) -> list[dict]:
    skill = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    fields, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    rel = f"{skill}/SKILL.md"
    out = _frontmatter_findings(skill, rel, fields, limits)
    lim = limits["body-max-lines"]
    n_body = len(body.strip("\n").split("\n")) if body.strip() else 0
    if n_body >= lim["value"]:  # Anthropic: "under 500 lines"
        out.append(_finding(skill, rel, lim, f"SKILL.md body is {n_body} lines, it must stay under {lim['value']}"))
    refs_dir = skill_dir / "references"
    refs = sorted(refs_dir.glob("*.md")) if refs_dir.is_dir() else []
    ref_names = {r.name for r in refs}
    linked_from_skill = _reference_targets(body, "", ref_names)
    texts = {"SKILL.md": body}
    for ref in refs:
        text = ref.read_text(encoding="utf-8")
        texts[f"references/{ref.name}"] = text
        rel_ref = f"{skill}/references/{ref.name}"
        lim = limits["references-one-level"]
        if ref.name not in linked_from_skill:
            out.append(_finding(skill, rel_ref, lim, "reference file is not linked from SKILL.md"))
        nested = sorted(_reference_targets(text, "references", ref_names) - {ref.name})
        if nested:
            out.append(_finding(skill, rel_ref, lim, f"links on to another reference file: {', '.join(nested)}"))
        lim = limits["reference-toc-threshold"]
        n = len(text.rstrip("\n").split("\n"))
        head = "\n".join(text.split("\n")[: lim["window"]])
        if n > lim["value"] and not re.search(r"^#+\s*(table of )?contents\b|\]\(#", head, re.I | re.M):
            out.append(_finding(skill, rel_ref, lim, f"{n} lines and no table of contents in the first {lim['window']}"))
    lim = limits["forward-slash-paths"]
    for fname, text in texts.items():
        if re.search(lim["value"], text):
            out.append(_finding(skill, f"{skill}/{fname}", lim, "backslash path (use forward slashes)"))
    return out


def find_skill_dirs(repo_root: Path) -> list[Path]:
    return sorted(p.parent for p in (repo_root / "plugins").glob("*/skills/*/SKILL.md"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--skill-dir", action="append", default=[], type=Path)
    ap.add_argument("--all", action="store_true", help="every plugins/*/skills/*/ under --repo-root")
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="fail on recommended findings too")
    args = ap.parse_args(argv)
    try:
        limits = load_limits(args.rules)
        dirs = list(args.skill_dir) + (find_skill_dirs(args.repo_root) if args.all else [])
        if not dirs:
            hint = f"no plugins/*/skills/*/SKILL.md under {args.repo_root.resolve()}" if args.all else "give --skill-dir or --all"
            print(f"error: {hint}", file=sys.stderr)
            return 2
        findings = [f for d in dirs for f in check_skill(d, limits)]
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"skills": len(dirs), "findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"[{f['kind']}] {f['file']}: {f['limit']}: {f['message']}")
        print(f"{len(dirs)} skill(s) checked, {len(findings)} finding(s)")
    hard = any(f["kind"] == "hard" for f in findings)
    return 1 if hard or (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
