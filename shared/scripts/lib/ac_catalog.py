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

__all__ = ["ac_body", "candidates", "catalog_texts", "fr_text", "load_catalog", "norm", "parse_catalog", "parse_fr_table", "words"]

_FR_HEAD = re.compile(r"^#{2,4}\s+(FR-\d+\.\d+)\s*[—–:-]*\s*(.*)$")  # "### FR-01.03 - Title" (this repo, adopted repos)
_FR_BOLD = re.compile(r"^\*\*(FR-\d+\.\d+)\s*[:—–-]\s*(.*?)\*\*\s*$")  # "**FR-01.03: Title**" (the greenfield generator)
_FR_ROW = re.compile(r"^\|\s*(FR-\d+\.\d+)\s*\|([^|]*)\|?")  # a requirements table row
_AC_MARKED = re.compile(r"^-\s+(?:\([A-Z]\)\s+)?\[AC(\d+)\]")
_AC_PLAIN = re.compile(r"^-\s+(?:\[[ xX]\]|\([A-Z]\))\s")  # "- [ ] text" (greenfield) or "- (E) text" (adopted, not yet minted)
_GENERIC_GROUPS = frozenset({"adopted"})  # what the adopt command writes for every FR of a brownfield repo: it names no part
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


def _split_name(rel: str) -> str:
    """``.shipwright/planning/02-web-ui/spec.md`` -> ``web-ui`` (the split the spec belongs to)."""
    return re.sub(r"^\d+-", "", rel.split("/")[-2])


def _spec_texts(root: Path, base_ref: str | None) -> list[tuple[str, str]]:
    """``[(split name, text)]`` for every ``.shipwright/planning/*/spec.md``: from ``base_ref`` when given (one ``git cat-file --batch``), else from the working tree."""
    if base_ref:
        names = run_git(root, "ls-tree", "-r", "--name-only", base_ref, ".shipwright/planning").decode("utf-8", "replace").splitlines()
        rels = sorted(n for n in names if re.fullmatch(r"\.shipwright/planning/[^/]+/spec\.md", n))
        blobs = read_blobs(root, base_ref, rels)
        missing = [r for r in rels if blobs[r] is None]
        if missing:
            raise RuntimeError(f"cannot read {missing[0]} at {base_ref}")
        return [(_split_name(r), blobs[r] or "") for r in rels]
    out = []
    for spec in sorted((root / ".shipwright" / "planning").glob("*/spec.md")):
        try:
            out.append((_split_name(spec.as_posix()), spec.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def load_catalog(project_root: str | Path, base_ref: str | None = None) -> dict:
    """``{"acs": {id: text}, "frs": {FR ids}, "titles": {FR id: title}, "unparsed": bool}``, from ``base_ref`` (git) when given.

    ``unparsed`` is true when there is no spec.md at all, or ANY spec has text but no FR this tool can read: callers SKIP then, they never ask, refuse or hold.
    """
    acs: dict[str, str] = {}
    titles: dict[str, str] = {}
    fr_texts: dict[str, str] = {}
    groups: dict[str, str] = {}
    texts = _spec_texts(Path(project_root), base_ref)
    unreadable = not texts  # no spec.md at all
    for split, text in texts:
        a, f = parse_catalog(text)
        acs.update(a)
        titles.update(f)
        for fr, row in parse_fr_table(text).items():
            fr_texts[fr] = row["description"]
            groups[fr] = row["area"] if row["area"].lower() not in _GENERIC_GROUPS else ""
        for fr in f:
            if not groups.get(fr) and split.lower() not in _GENERIC_GROUPS:
                groups[fr] = split  # no area column: the split the spec lives in is the project's own grouping
        unreadable = unreadable or (bool(text.strip()) and not f)  # ANY spec with text but no readable FR
    return {"acs": acs, "frs": set(titles), "titles": titles, "fr_text": fr_texts, "groups": {k: v for k, v in groups.items() if v}, "unparsed": unreadable}


def parse_fr_table(spec_text: str) -> dict[str, dict[str, str]]:
    """``{"FR-01.03": {"area": ..., "description": ...}}`` from the requirements table (its header row names the columns: ID, Area, Description)."""
    cols: dict[str, int] = {}
    out: dict[str, dict[str, str]] = {}
    for line in (spec_text or "").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0].lower() == "id":
            cols = {c.lower(): i for i, c in enumerate(cells)}
        elif cols and re.fullmatch(r"FR-\d+\.\d+", cells[0]):
            out[cells[0]] = {k: _norm(cells[cols[k]]) if k in cols and cols[k] < len(cells) else "" for k in ("area", "description")}
    return out


def fr_text(fr: str, cat: dict) -> str:
    """The requirement's own text from the spec: the table's Description when there is one, else its heading title; empty when unknown."""
    return _norm((cat.get("fr_text") or {}).get(fr)) or _norm((cat.get("titles") or {}).get(fr))


def words(text: str) -> set[str]:
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP}


def candidates(text: str, cat: dict, limit: int = 3) -> list[tuple[str, str]]:
    """The FRs whose title or criteria share the most words with ``text``: ``[(fr id, title)]``, best first (deterministic)."""
    want = words(text)
    pool: dict[str, set[str]] = {}
    for ac, body in cat.get("acs", {}).items():
        pool.setdefault(ac.rsplit(".AC", 1)[0], set()).update(words(body))
    scored = []
    for fr, title in cat.get("titles", {}).items():
        score = 3 * len(want & words(title)) + len(want & pool.get(fr, set()))
        if score:
            scored.append((-score, fr, title))
    return [(fr, title) for _, fr, title in sorted(scored)[:limit]]
