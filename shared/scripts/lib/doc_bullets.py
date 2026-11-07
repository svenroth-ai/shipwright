"""Conventions / architecture bullets as per-run drop files (issue 978, S5).

Today every iterate appends its one-line bullet to ``architecture.md`` /
``conventions.md`` -- two PRs touching the same section conflict on GitHub. A bullet drop is a
file of its own, so two branches only ever ADD different files:

    .shipwright/agent_docs/decision-drops/bullets/<target>--<key>--<wt8>--<nonce8>.md

``<target>`` is ``architecture`` | ``conventions`` | ``learnings``; the file holds ONE bullet line.
The subfolder AND the ``.md`` suffix hide it from every consumer of the ADR drops (the
non-recursive ``*.json`` globs of ``aggregate_decisions``, ``architecture_doc.scan_drops``,
``decision_drops_index`` and the WebUI reader), so an old plugin or an old WebUI never turns a
bullet into an ADR (DESIGN 4.3). No layout flag: old consumers cannot see these files.

Three readers share this module so they cannot disagree:

* :func:`effective_text` -- the doc with the pending bullets inserted exactly where :func:`fold`
  would put them, so every budget / shape / "is run X documented" check sees folded + pending and
  a render of the pending state equals a render of the folded state byte for byte;
* :func:`fold` -- the release step: insert into the curated section, delete the drop files;
* :func:`render_pending_summary` -- context load: the 20 newest, ``N more pending``, a warning above 40.

Pure file I/O; never shells out to git.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

try:
    from .agent_doc_budget import entry_anchor, entry_date, iter_entries
except ImportError:  # loaded by file path with no parent package (audit_adapters.load_shared_lib)
    import hashlib
    import importlib.util
    import sys

    _src = Path(__file__).resolve().parent / "agent_doc_budget.py"
    _name = "_shipwright_doc_bullets_budget_" + hashlib.sha256(str(_src.parent).encode("utf-8")).hexdigest()[:12]
    _mod = sys.modules.get(_name)
    if _mod is None:
        _spec = importlib.util.spec_from_file_location(_name, _src)
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[_name] = _mod
        try:
            _spec.loader.exec_module(_mod)
        except BaseException:
            sys.modules.pop(_name, None)
            raise
    entry_anchor, entry_date, iter_entries = _mod.entry_anchor, _mod.entry_date, _mod.iter_entries

DROP_DIRNAME = "decision-drops"
BULLETS_DIRNAME = "bullets"
CONTEXT_LIMIT = 20
WARN_ABOVE = 40

# target -> (doc filename under .shipwright/agent_docs/, section header). Same sections as
# ``agent_doc_budget.SECTIONS``; the routing for impacts stays ``architecture_doc.IMPACT_TARGETS``.
TARGETS: dict[str, tuple[str, str]] = {
    "architecture": ("architecture.md", "## Architecture Updates"),
    "conventions": ("conventions.md", "## Convention Updates"),
    "learnings": ("conventions.md", "## Learnings"),
}
_NAME = re.compile(
    r"^(" + "|".join(TARGETS) + r")--([A-Za-z0-9._-]{1,80})--([0-9a-f]{8})--([0-9a-f]{8})\.md$"
)


@dataclass(frozen=True)
class Bullet:
    target: str
    key: str
    text: str
    path: Path


def bullets_dir(project_root: Path | str) -> Path:
    return Path(project_root) / ".shipwright" / "agent_docs" / DROP_DIRNAME / BULLETS_DIRNAME


def _sort_key(b: Bullet) -> tuple:
    return (entry_date(b.text) or date.min, b.key, b.path.name)


def parse_bullet(name: str, content: str, path: Path | None = None) -> Bullet | None:
    """The bullet in file ``name`` with ``content``, or ``None`` when it is not the bullet grammar."""
    m = _NAME.match(name)
    text = content.replace("\r\n", "\n").strip("\n")
    if not m or not text.startswith("- ") or len(text.splitlines()) != 1:
        return None
    return Bullet(m.group(1), m.group(2), text, path or Path(name))


def fold_named(text: str, filename: str, items: list[tuple[str, str]]) -> str:
    """``text`` with bullets given as ``(file name, content)`` pairs folded in (e.g. read at a git base)."""
    parsed = [b for b in (parse_bullet(n, c) for n, c in items) if b]
    return _fold_text(text, filename, sorted(parsed, key=_sort_key))


def pending(project_root: Path | str, target: str | None = None) -> tuple[list[Bullet], list[str]]:
    """``(bullets, skipped_names)`` -- valid pending bullets oldest first, and the names ignored.

    A file is skipped (named, never raised on) when its name is not the bullet grammar, it is a
    symlink or empty, or its first line is not a ``- `` bullet. ``.gitkeep`` is not reported.
    """
    bd = bullets_dir(project_root)
    if not bd.is_dir():
        return [], []
    found: list[Bullet] = []
    skipped: list[str] = []
    for f in sorted(bd.iterdir()):
        if f.name == ".gitkeep":
            continue
        if f.is_symlink() or not f.is_file():
            skipped.append(f.name)
            continue
        try:
            b = parse_bullet(f.name, f.read_text(encoding="utf-8"), f)
        except (OSError, UnicodeDecodeError):
            b = None
        if b is None:
            skipped.append(f.name)
        elif target is None or b.target == target:
            found.append(b)
    return sorted(found, key=_sort_key), skipped


def bullet_files_for_run(project_root: Path | str, key: str) -> list[Path]:
    """This run's own bullet files (name key == ``key``); what F6 stages and F11 checks."""
    return [b.path for b in pending(project_root)[0] if b.key == key]


def insert_bullets(text: str, header: str, bullets: list[str]) -> str:
    """Insert ``bullets`` at the end of ``header``'s section (appended, section created if absent).

    A bullet whose anchor is already an entry of the section is NOT inserted again (re-fold
    safety). With nothing to insert the text comes back untouched.
    """
    have = {entry_anchor(e) for e in iter_entries(text, header)}
    fresh: list[str] = []
    for b in bullets:
        if entry_anchor(b) not in have:
            have.add(entry_anchor(b))
            fresh.append(b)
    if not fresh:
        return text
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.strip() == header), None)
    block = [eol.join(b.split("\n")) + eol for b in fresh]
    if start is None:
        head = "".join(lines)
        if head and not head.endswith(("\n", "\r")):
            head += eol
        head += eol if head else ""
        return head + header + eol + eol + "".join(block)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    at = end
    while at > start + 1 and not lines[at - 1].strip():
        at -= 1
    if at == start + 1:
        block.insert(0, eol)
    if not lines[at - 1].endswith(("\n", "\r")):
        lines[at - 1] += eol
    return "".join(lines[:at] + block + lines[at:])


def _conflicts(text: str, header: str, bullets: list[Bullet]) -> list[Bullet]:
    """Bullets that would be dropped by the anchor dedup although their text DIFFERS from the winner."""
    seen = {entry_anchor(e): e for e in iter_entries(text, header)}
    out: list[Bullet] = []
    for b in bullets:
        a = entry_anchor(b.text)
        if a not in seen:
            seen[a] = b.text
        elif seen[a] != b.text:
            out.append(b)
    return out


def _fold_text(text: str, filename: str, bullets: list[Bullet]) -> str:
    for target, (fname, header) in TARGETS.items():
        if fname == filename:
            text = insert_bullets(text, header, [b.text for b in bullets if b.target == target])
    return text


def effective_text(agent_docs_dir: Path | str, filename: str) -> str:
    """``filename``'s text with pending bullets folded in; ``""`` when unreadable and none pending."""
    agent_docs_dir = Path(agent_docs_dir)
    bullets, _ = pending(agent_docs_dir.parent.parent)
    mine = [b for b in bullets if TARGETS[b.target][0] == filename]
    try:
        if not mine:
            return (agent_docs_dir / filename).read_text(encoding="utf-8", errors="ignore")
        # Bytes, exactly like fold(): the pending render equals the folded bytes, CRLF included.
        text = (agent_docs_dir / filename).read_bytes().decode("utf-8", errors="ignore")
    except OSError:
        text = ""
    return _fold_text(text, filename, mine)


def fold(project_root: Path | str, *, dry_run: bool = False) -> dict:
    """Release step: fold every pending bullet into its doc, then delete the files folded.

    A doc that cannot be written keeps its bullet files (nothing is lost, the next release
    retries). Run BEFORE the ADR fold so the architecture fallback bullet is not duplicated.
    """
    from .atomic_write import durable_atomic_write
    from .file_lock import file_lock

    root = Path(project_root)
    docs = root / ".shipwright" / "agent_docs"
    bullets, skipped = pending(root)
    result: dict = {"folded": 0, "files": [], "errors": [], "conflicts": [], "skipped": skipped, "dry_run": dry_run}
    for filename in dict.fromkeys(fname for fname, _ in TARGETS.values()):
        mine = [b for b in bullets if TARGETS[b.target][0] == filename]
        if not mine:
            continue
        doc = docs / filename
        try:
            with file_lock(str(doc) + ".lock", timeout_seconds=10.0):
                old = doc.read_bytes().decode("utf-8") if doc.exists() else ""  # bytes: keep CRLF
                new = _fold_text(old, filename, mine)
                # Same anchor, different text: keep the file for a human, never delete unwritten text.
                clash = [b for t, (f, h) in TARGETS.items() if f == filename
                         for b in _conflicts(old, h, [x for x in mine if x.target == t])]
                for b in clash:
                    result["conflicts"].append(b.path.name)
                mine = [b for b in mine if b not in clash]
                if not dry_run:
                    if new != old:
                        durable_atomic_write(doc, new.encode("utf-8"))
                    for b in mine:
                        b.path.unlink()
        except (OSError, UnicodeDecodeError, RuntimeError) as exc:
            result["errors"].append(f"{filename}: {exc}")
            continue
        result["folded"] += len(mine)
        result["files"] += [b.path.name for b in mine]
    return result


def render_pending_summary(
    project_root: Path | str, limit: int = CONTEXT_LIMIT, warn_above: int = WARN_ABOVE,
) -> str:
    """Context-load view: the ``limit`` newest pending bullets, ``N more pending``, a cap warning."""
    bullets, _ = pending(project_root)
    if not bullets:
        return ""
    shown = bullets[::-1][:limit]
    out = [f"- [{b.target}] {b.text[2:140]}" for b in shown]
    if len(bullets) > limit:
        out.append(f"... {len(bullets) - limit} more pending (not shown)")
    if len(bullets) > warn_above:
        out.append(
            f"WARNING: {len(bullets)} pending bullets (> {warn_above}) -- "
            "they fold at /shipwright-changelog (or run tools/fold_bullets.py)"
        )
    return "\n".join(out)
