"""Reading the requirement catalog (``spec.md``) in every shape the product writes, from a git ref.

The shapes: ``### FR-01.03 - Title`` (this repo and adopted repos), the greenfield generator's
``**FR-01.03: Title**`` and requirement-table rows; criteria ``- [AC05] ...`` / ``- (E) [AC05] ...`` (the marker is the
id), unmarked ``- (E) ...`` and ``- [ ] ...`` (numbered by position, the order the id minter gives). A catalog that has
text but no readable FR is flagged ``unparsed`` so callers skip instead of asking or refusing. Stdlib only.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib.ac_surface import read_blobs, run_git

__all__ = ["ac_body", "area_blurb", "candidates", "catalog_texts", "load_catalog", "norm", "parse_catalog"]

_FR_HEAD = re.compile(r"^#{2,4}\s+(FR-\d+\.\d+)\s*[—–:-]*\s*(.*)$")  # "### FR-01.03 - Title" (this repo, adopted repos)
_FR_BOLD = re.compile(r"^\*\*(FR-\d+\.\d+)\s*[:—–-]\s*(.*?)\*\*\s*$")  # "**FR-01.03: Title**" (the greenfield generator)
_FR_ROW = re.compile(r"^\|\s*(FR-\d+\.\d+)\s*\|([^|]*)\|?")  # a requirements table row
_AC_MARKED = re.compile(r"^-\s+(?:\([A-Z]\)\s+)?\[AC(\d+)\]")
_AC_PLAIN = re.compile(r"^-\s+(?:\[[ xX]\]|\([A-Z]\))\s")  # "- [ ] text" (greenfield) or "- (E) text" (adopted, not yet minted)
_STOP = frozenset("this that with from when then given have been will into than their there which what where while must does each also only more some such over under after before about other without within".split())


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


norm = _norm


def ac_body(text: object) -> str:
    """An AC's wording without list markup (``- (E) [AC05]``, ``- [ ]``) and the trailing run-id note, lower-cased."""
    body = re.sub(r"^-?\s*(?:\[[ xX]\]\s*)?(?:\([A-Z]\)\s*)?(?:\[AC\d+\]\s*)?(?:\*\*\(iterate-[^)]*\)\*\*\s*)?", "", _norm(text))
    return re.sub(r"\s*\(iterate-[^)]*\)\s*$", "", body).strip().lower()


def parse_catalog(spec_text: str) -> tuple[dict[str, str], dict[str, str]]:
    """``(acs, frs)``: ``{"FR-01.03.AC05": text}`` and ``{"FR-01.03": title}`` for one ``spec.md``, in every shape the product writes.

    FR headings: ``### FR-01.03 - Title``, the greenfield ``**FR-01.03: Title**``, and table rows (``| FR-01.03 | ...``).
    Criteria: ``- [AC05] ...`` / ``- (E) [AC05] ...`` (the id is the marker), and unmarked ``- [ ] ...`` / ``- (E) ...``
    (numbered by position, the order the id minter would give them).
    """
    out: dict[str, str] = {}
    frs: dict[str, str] = {}
    fr, cur, last = "", "", 0
    for line in (spec_text or "").splitlines():
        h = _FR_HEAD.match(line) or _FR_BOLD.match(line)
        row = _FR_ROW.match(line)
        marked, plain = _AC_MARKED.match(line), _AC_PLAIN.match(line)
        if row:
            frs.setdefault(row.group(1), row.group(2).strip())
        if h or marked or plain or line.startswith("#"):
            cur = ""
        if h:
            fr, last = h.group(1), 0
            frs[fr] = h.group(2).strip()
        elif line.startswith("## "):
            fr = ""
        elif (marked or plain) and fr:
            last = int(marked.group(1)) if marked else last + 1
            cur = f"{fr}.AC{last:02d}"
            out[cur] = line
        elif cur and line.startswith(" "):
            out[cur] += " " + line.strip()
        elif cur and line.strip():
            cur = ""
    return {k: _norm(v) for k, v in out.items()}, frs


def catalog_texts(spec_text: str) -> dict[str, str]:
    """``{"FR-01.03.AC05": "its text", ...}`` for one ``spec.md``."""
    return parse_catalog(spec_text)[0]


def _spec_texts(root: Path, base_ref: str | None) -> list[str]:
    """Every ``.shipwright/planning/*/spec.md``: from ``base_ref`` when given (one ``git cat-file --batch``), else from the working tree."""
    if base_ref:
        names = run_git(root, "ls-tree", "-r", "--name-only", base_ref, ".shipwright/planning").decode("utf-8", "replace").splitlines()
        rels = sorted(n for n in names if re.fullmatch(r"\.shipwright/planning/[^/]+/spec\.md", n))
        blobs = read_blobs(root, base_ref, rels)
        missing = [r for r in rels if blobs[r] is None]
        if missing:
            raise RuntimeError(f"cannot read {missing[0]} at {base_ref}")
        return [blobs[r] or "" for r in rels]
    out = []
    for spec in sorted((root / ".shipwright" / "planning").glob("*/spec.md")):
        try:
            out.append(spec.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def load_catalog(project_root: str | Path, base_ref: str | None = None) -> dict:
    """``{"acs": {id: text}, "frs": {FR ids}, "titles": {FR id: title}, "unparsed": bool}``, from ``base_ref`` (git) when given.

    ``unparsed`` is true when a spec has text but no FR could be read from it: callers SKIP then, they never ask or refuse.
    """
    acs: dict[str, str] = {}
    titles: dict[str, str] = {}
    texts = _spec_texts(Path(project_root), base_ref)
    for text in texts:
        a, f = parse_catalog(text)
        acs.update(a)
        titles.update(f)
    return {"acs": acs, "frs": set(titles), "titles": titles, "unparsed": bool(not titles and any(t.strip() for t in texts))}


def _words(text: str) -> set[str]:
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP}


def candidates(text: str, cat: dict, limit: int = 3) -> list[tuple[str, str]]:
    """The FRs whose title or criteria share the most words with ``text``: ``[(fr id, title)]``, best first (deterministic)."""
    want = _words(text)
    pool: dict[str, set[str]] = {}
    for ac, body in cat.get("acs", {}).items():
        pool.setdefault(ac.rsplit(".AC", 1)[0], set()).update(_words(body))
    scored = []
    for fr, title in cat.get("titles", {}).items():
        score = 3 * len(want & _words(title)) + len(want & pool.get(fr, set()))
        if score:
            scored.append((-score, fr, title))
    return [(fr, title) for _, fr, title in sorted(scored)[:limit]]


def area_blurb(fr: str, cat: dict, width: int = 110) -> str:
    """A one-line description of an area: the OUTCOME clause (after ", then") of its first criterion, kept only when it is short and complete (otherwise empty: the area is then shown by name alone)."""
    first = next((body for ac, body in sorted(cat.get("acs", {}).items()) if ac.rsplit(".AC", 1)[0] == fr), "")
    text = re.sub(r"\s*\(iterate-[^)]*\)", "", re.sub(r"^-?\s*(?:\[[ xX]\]\s*)?(?:\([A-Z]\)\s*)?(?:\[AC\d+\]\s*)?(?:\*\*\(iterate-[^)]*\)\*\*\s*)?", "", _norm(first))).strip()
    text = text.split(", then ", 1)[1] if ", then " in text else re.sub(r"^given\s+", "", text, flags=re.IGNORECASE)
    text = text.strip().rstrip(".")
    if not text:
        return ""
    text = re.split(r"\s+[—–]\s+", text, maxsplit=1)[0].strip()
    if not text or len(text) > width:
        return ""  # a half-sentence would read worse than the area's name alone
    return text[0].upper() + text[1:] + "."
