"""What Design places from a Brief package, shared by its writer and its verifier (campaign
brief-driven-run, B3a).

* the design plugin's ``apply-brief-package.py`` plans the files it writes with :func:`plan_screens`;
* ``verifiers/brief_design_checks.py`` re-derives the SAME plan from the package and the minted FR
  rows to prove that Design applied the package instead of re-typing it.

A ``screen-map.json`` entry is ``{id, mockup, requirements: [capability slug, ...]}``. The slugs are the
lower-kebab form of the FR ``Name`` the brief headings give; the FR ids are the ones Project MINTED in
``.shipwright/planning/<split>/spec.md``. Nobody picks an id here.

No ``lib`` import (the verifier runs inside other plugins' validators, ADR-045).
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.grill_trace_fr_coverage import extract_fr_names, slugify

_REQ_COMMENT_RE = re.compile(r"<!--\s*Requirements:(.*?)-->", re.IGNORECASE | re.DOTALL)
_FR_ID_RE = re.compile(r"^FR-\d{1,3}\.\d{1,3}$")
_SNIFF_BYTES = 8192


def same_content(a: bytes, b: bytes) -> bool:
    """Equality under the package hash's own rule: CRLF -> LF for text (no NUL early on), exact otherwise."""
    def norm(raw: bytes) -> bytes:
        return raw.replace(b"\r\n", b"\n") if 0 not in raw[:_SNIFF_BYTES] else raw

    return norm(a) == norm(b)


def fr_ids_by_slug(project_root: Path) -> dict[str, list[str]]:
    """``{slug of the FR Name: [FR ids]}`` (more than one id = ambiguous) from the live FR rows of every split's spec.md."""
    out: dict[str, list[str]] = {}
    planning = Path(project_root) / ".shipwright" / "planning"
    for spec in sorted(planning.glob("*/spec.md")) if planning.is_dir() else []:
        if spec.parent.name == "iterate":
            continue
        for fr_id, name in extract_fr_names(spec.read_text(encoding="utf-8", errors="ignore")).items():
            ids = out.setdefault(slugify(name), [])
            if fr_id not in ids:
                ids.append(fr_id)
    return out


def screen_file_name(idx: int, entry: dict) -> str:
    return f"{idx:02d}-{slugify(str(entry.get('id') or ''))}.html"


def plan_screens(bdir: Path, screen_map: dict, by_slug: dict[str, list[str]]) -> tuple[list[dict], list[dict]]:
    """``(planned screens, issues)``: every entry resolved to files and FR ids, or an issue."""
    plan: list[dict] = []
    issues: list[dict] = []
    seen: set[str] = set()
    seen_mockups: set[str] = set()
    for idx, entry in enumerate(screen_map.get("screens") or [], start=1):
        reqs = entry.get("requirements") if isinstance(entry, dict) else None
        if not isinstance(reqs, list) or not all(isinstance(r, str) for r in reqs):
            issues.append({"code": "bad_screen_map_entry", "screen": f"#{idx}",
                           "message": "a screen-map entry must be an object whose requirements is a list of capability slugs"})
            continue
        sid = slugify(str(entry.get("id") or ""))
        mock = str(entry.get("mockup") or "")
        src = bdir / "mockups" / mock
        wanted = [slugify(r) for r in reqs]
        frs = [by_slug[s][0] for s in wanted if len(by_slug.get(s, ())) == 1]
        problems = (
            ([f"screen id {entry.get('id')!r} is empty or repeated"] if not sid or sid in seen else [])
            + ([f"mockup {mock!r} is not an .html file (a screen is HTML)"] if not mock.lower().endswith(".html") else [])
            + ([f"mockup {mock!r} must be a plain file name inside mockups/"] if mock != Path(mock).name or mock in ("", ".", "..") else [])
            + ([f"mockup {mock!r} is missing"] if not src.is_file() else [])
            + [f"requirement {s!r} has no FR row in any spec.md (Project mints the ids)" for s in wanted if s not in by_slug]
            + [f"requirement {s!r} matches several FR rows {by_slug[s]}: ambiguous" for s in wanted if len(by_slug.get(s, ())) > 1]
            + ([] if wanted else ["no requirements: a screen must link at least one"])
        )
        seen.add(sid)
        if mock.casefold() in seen_mockups:
            problems.append(f"mockup {mock!r} is used by two screens")
        seen_mockups.add(mock.casefold())
        issues += [{"code": "bad_screen_map_entry", "screen": sid or f"#{idx}", "message": m} for m in problems]
        if not problems:
            plan.append({"id": sid, "mockup": mock, "src": src, "frs": list(dict.fromkeys(frs)),
                         "screen_file": screen_file_name(idx, entry)})
    return plan, issues


def linked_frs(html: str) -> set[str]:
    """Every FR id named by any ``<!-- Requirements: ... -->`` comment of a screen."""
    ids: set[str] = set()
    for match in _REQ_COMMENT_RE.finditer(html):
        ids |= {t.strip() for t in match.group(1).split(",") if _FR_ID_RE.match(t.strip())}
    return ids


def applied_file_issues(bdir: Path, designs: Path, screen_map: dict) -> list[dict]:
    """Issues for an applied package whose files went missing: an upload must still equal the package
    (hash rule), a screen must still exist (its content may have been edited in the review loop)."""
    issues = []
    for idx, entry in enumerate(screen_map.get("screens") or [], start=1):
        mock = str(entry.get("mockup") or "")
        upload, screen = designs / "uploads" / mock, designs / "screens" / screen_file_name(idx, entry)
        if not upload.is_file() or not same_content(upload.read_bytes(), (bdir / "mockups" / mock).read_bytes()):
            issues.append({"code": "applied_files_missing", "screen": mock,
                           "message": f"uploads/{mock} is missing or no longer matches the package"})
        if not screen.is_file():
            issues.append({"code": "applied_files_missing", "screen": screen.name, "message": f"screens/{screen.name} is missing"})
    return issues
