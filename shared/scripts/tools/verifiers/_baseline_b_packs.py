"""Blind label packs (BP unit BL0b, item 7).

A pack holds ONLY: the PR title, the production and test diff (documentation, evidence and generated files are listed by
name and left out of the diff; long diffs are cut per file and overall, with a marker), and the FR catalog (id + one-line
statement). The ACs of every FR are in one shared file (``FR_CATALOG.md``, the same for every pack). A pack never names the
author's declaration (``affected_frs``), the git leg's result, T-code's result or the path baseline's: the strata live outside
the labels folder.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._baseline_touch_git import GitRev

__all__ = ["catalog", "build_pack", "write_catalog"]

_OMIT = re.compile(r"^(\.shipwright/|CHANGELOG|docs/|shipwright_events|.*\.lock$|.*package-lock\.json$)")
_FILE_CAP, _TOTAL_CAP = 120, 700
_ROW = re.compile(r"^\|\s*(FR-\d{2}\.\d{2})\s*\|\s*[^|]*\|\s*([^|]*?)\s*\|\s*[^|]*\|\s*(.*?)\s*\|[^|]*\|[^|]*\|\s*$")


def catalog(spec_text: str) -> list[dict]:
    """``[{id, name, statement, acs: [(AC id, text)]}]`` from the adopted spec."""
    rows = {m[1]: (m[2], m[3]) for line in spec_text.splitlines() if (m := _ROW.match(line))}
    sections = re.split(r"(?m)^### (FR-\d{2}\.\d{2}) .*$", spec_text)
    acs: dict[str, list[tuple[str, str]]] = {}
    for fr, body in zip(sections[1::2], sections[2::2]):
        body = re.split(r"(?m)^## ", body)[0]
        items = re.split(r"(?m)^- ", body)[1:]
        acs[fr] = [(m[1], re.sub(r"\s+", " ", m[2]).strip()) for it in items if (m := re.match(r"(?:\([A-Z]\)\s*)?\[(AC\d+)\]\s*(.*)", it, re.S))]
    return [{"id": fr, "name": name, "statement": desc, "acs": acs.get(fr, [])} for fr, (name, desc) in sorted(rows.items())]


def write_catalog(cat: list[dict], path: Path) -> None:
    lines = ["# FR catalog (identical for every pack)", "", "Every requirement with its acceptance criteria. Ids only; no author or tool output.", ""]
    for fr in cat:
        lines += [f"## {fr['id']} - {fr['name']}", "", fr["statement"], ""] + [f"- [{a}] {t}" for a, t in fr["acs"]] + [""]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _diff(rev: GitRev, path_old: str, path_new: str) -> str:
    args = ["diff", "--no-ext-diff", "--no-color", "-U3", "-M", rev.base, rev.head, "--", path_old, *([path_new] if path_new != path_old else [])]
    return rev.git(*args)[1]


def build_pack(rev: GitRev, title: str, pr: int, cat: list[dict]) -> str:
    changes = rev.changed()
    shown, omitted = [], []
    for status, old, new in changes:
        (omitted if _OMIT.match(new) or _OMIT.match(old) else shown).append((status, old, new))
    shown.sort(key=lambda c: (("/tests/" in c[2] or c[2].startswith("integration-tests/")), c[2]))
    stat = {}
    for line in rev.git("diff", "--no-ext-diff", "--numstat", "-M", rev.base, rev.head)[1].splitlines():
        a, d, name = (line.split("\t") + ["", "", ""])[:3]
        stat[name] = (a, d)
    title = re.sub(r"FR-\d{2}\.\d{2}(?:/AC\d+)?(?: AC\d+)?", "FR-xx", title)  # a title may name the author's FR: redacted
    out = [f"# PR {pr}", "", f"Title: {title}", "", "## Files changed (production and tests)", ""]
    out += [f"- {s} {n}  (+{stat.get(n, ('?', '?'))[0]} -{stat.get(n, ('?', '?'))[1]})" for s, _o, n in shown] or ["- (none)"]
    if omitted:
        out += ["", f"{len(omitted)} documentation / evidence / generated file(s) not shown: " + ", ".join(n for _s, _o, n in omitted[:8]) + (" ..." if len(omitted) > 8 else "")]
    out += ["", "## Diff (production first, then tests)", ""]
    budget = _TOTAL_CAP
    for status, old, new in shown:
        text = _diff(rev, old, new).splitlines()
        if not text:
            continue
        if budget <= 0:
            out.append(f"\n[diff of {new} omitted: overall size cap reached]")
            continue
        keep = text[: min(_FILE_CAP, budget)]
        budget -= len(keep)
        out += ["```diff", *keep, "```"] + ([f"[... {len(text) - len(keep)} more diff lines of {new} cut]"] if len(text) > len(keep) else [])
    out += ["", "## FR catalog (id: statement)", ""] + [f"- {fr['id']} ({fr['name']}): {fr['statement']}" for fr in cat]
    out += ["", "Acceptance criteria of every FR (ids and text): see FR_CATALOG.md next to this file.", ""]
    return "\n".join(out)
