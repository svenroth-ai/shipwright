"""Entry-budget + routing-SSoT guards for the always-loaded agent docs.

Two structural guards that keep the Layer-1 agent docs lean and consistently
routed (the agent-doc-entry-rules split, 2026-06-12). They make the progressive-
disclosure rule enforceable rather than advisory:

1. ENTRY BUDGET (forward-only). Each DATED entry under ``## Architecture
   Updates`` (architecture.md) and ``## Convention Updates`` / ``## Learnings``
   (conventions.md) authored on/after ``_ENFORCED_FROM`` must be
   ``<= _ENTRY_MAX_CHARS``. Detail belongs ONCE in the on-demand ADR /
   ``.shipwright/planning/adr/`` spec folder; the always-loaded docs carry a
   one-line "what + pointer to the ADR". Mirrors the per-field budget already
   enforced on ``decision_log.md`` (``write_decision_log.ADR_FIELD_MAX_CHARS``).
   Entries dated before the cutoff (and undated legacy entries) are
   grandfathered — the follow-up compression iterate shrinks the backlog.

2. ROUTING SSoT. The impact -> (target doc, section) mapping is defined once in
   ``lib.architecture_doc.IMPACT_TARGETS`` and consumed by the oracle (F11 gate
   + Group-F detective), the producer (``write_decision_log``), and the F2.md
   instruction. These tests pin producer + instruction to the SSoT so the three
   cannot silently diverge again (``convention`` was being hand-routed to
   architecture.md while the writer routed it to conventions.md).
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "tools"))

import write_decision_log  # noqa: E402
from lib.architecture_doc import IMPACT_TARGETS, REAL_IMPACTS  # noqa: E402

# One-line "what + pointer". 600 chars ~ a self-contained sentence plus a key
# surface path and an ADR pointer — generous vs. the typical ~100-300 char
# compact entry, tight enough to forbid the multi-hundred-word paragraphs.
_ENTRY_MAX_CHARS = 600

# Enforcement boundary: every entry authored on/after this date must comply.
# Lowered from 2026-06-13 to 2026-05-01 by iterate-2026-06-12-compress-agent-doc-
# backlog, which compacted the whole backlog (architecture.md `## Architecture
# Updates` + conventions.md `## Convention Updates` / `## Learnings`) to one-line
# pointers and archived the verbatim detail under `.shipwright/planning/adr/`. The
# date sits just before the earliest dated backlog entry (2026-05-02), so the gate
# now enforces the entire compacted corpus rather than only forward-dated entries.
# (Undated entries — e.g. `(2026-06-11, iterate ...)` forms that the strict
# `(YYYY-MM-DD)` regex does not match — remain exempt by construction.)
_ENFORCED_FROM = date(2026, 5, 1)

_AGENT_DOCS = _REPO_ROOT / ".shipwright" / "agent_docs"
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("architecture.md", "## Architecture Updates"),
    ("conventions.md", "## Convention Updates"),
    ("conventions.md", "## Learnings"),
)

_DATE_RE = re.compile(r"\((\d{4})-(\d{2})-(\d{2})\)")


def iter_entries(text: str, section_header: str) -> list[str]:
    """Yield each top-level ``- `` bullet block under ``section_header``.

    An entry is a top-level ``- `` bullet at column 0 plus its continuation
    lines (deeper indentation / blank lines) up to the next top-level bullet or
    the next ``## `` heading. Returns the joined entry text (trailing
    whitespace stripped) for each entry.
    """
    lines = text.splitlines()
    # Find the section body.
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == section_header:
            start = i + 1
            break
    if start is None:
        return []
    entries: list[str] = []
    cur: list[str] | None = None
    for ln in lines[start:]:
        if ln.startswith("## "):
            break
        if ln.startswith("- "):
            if cur is not None:
                entries.append("\n".join(cur).rstrip())
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
    if cur is not None:
        entries.append("\n".join(cur).rstrip())
    return entries


def entry_date(entry: str) -> date | None:
    """First ``(YYYY-MM-DD)`` token in ``entry`` as a date, else None."""
    m = _DATE_RE.search(entry)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _enforced_violations(entries: list[str]) -> list[str]:
    """Entries authored on/after the cutoff that exceed the char budget."""
    bad: list[str] = []
    for e in entries:
        d = entry_date(e)
        if d is not None and d >= _ENFORCED_FROM and len(e) > _ENTRY_MAX_CHARS:
            head = e.splitlines()[0][:80]
            bad.append(f"{len(e)} chars (> {_ENTRY_MAX_CHARS}): {head}…")
    return bad


# --- entry budget (real files, forward-only) --------------------------------


@pytest.mark.parametrize("filename,header", _SECTIONS)
def test_new_entries_within_budget(filename: str, header: str):
    """Every entry authored on/after _ENFORCED_FROM is a one-line pointer
    (<= _ENTRY_MAX_CHARS). Pre-cutoff + undated legacy entries are exempt."""
    path = _AGENT_DOCS / filename
    if not path.exists():
        pytest.skip(f"{filename} absent")
    entries = iter_entries(path.read_text(encoding="utf-8", errors="ignore"), header)
    violations = _enforced_violations(entries)
    if violations:
        pytest.fail(
            f"{filename} '{header}' has over-budget entries authored on/after "
            f"{_ENFORCED_FROM.isoformat()} — keep each entry a one-line 'what + "
            f"ADR pointer'; move detail into the ADR / .shipwright/planning/adr/ "
            "spec folder (see references/F2.md, references/reflection.md):\n  - "
            + "\n  - ".join(violations)
        )


# --- entry budget (hermetic — proves the gate discriminates) ----------------


def test_iter_entries_splits_top_level_bullets():
    text = (
        "## Architecture Updates\n\n"
        "- **a** (2026-06-13): one\n  continued line\n"
        "- **b** (2026-06-13): two\n\n"
        "## Next\n- **c**: ignored\n"
    )
    entries = iter_entries(text, "## Architecture Updates")
    assert len(entries) == 2
    assert entries[0].startswith("- **a**") and "continued line" in entries[0]
    assert entries[1].startswith("- **b**")


def test_over_budget_dated_entry_is_flagged():
    after = (_ENFORCED_FROM + timedelta(days=1)).isoformat()
    big = f"- **x** ({after}): " + ("y" * (_ENTRY_MAX_CHARS + 50))
    assert _enforced_violations([big])


def test_grandfathered_entries_exempt():
    # Dates computed relative to the cutoff so the hermetic cases survive a future
    # _ENFORCED_FROM change: a pre-cutoff dated entry and an undated entry are exempt.
    before = (_ENFORCED_FROM - timedelta(days=1)).isoformat()
    big_old = f"- **x** ({before}): " + ("y" * (_ENTRY_MAX_CHARS + 50))
    big_undated = "- **x**: " + ("y" * (_ENTRY_MAX_CHARS + 50))
    assert _enforced_violations([big_old]) == []
    assert _enforced_violations([big_undated]) == []


# --- routing SSoT: producer matches IMPACT_TARGETS --------------------------


def _seed_doc(proj: Path, filename: str, header: str) -> None:
    doc = proj / ".shipwright" / "agent_docs"
    doc.mkdir(parents=True, exist_ok=True)
    (doc / filename).write_text(f"# {filename}\n\n{header}\n", encoding="utf-8")


@pytest.mark.parametrize("impact", sorted(REAL_IMPACTS))
def test_writer_routes_per_impact_targets(tmp_path: Path, impact: str):
    """write_decision_log._append_architecture_update lands the bullet in the
    file + section IMPACT_TARGETS prescribes — and nowhere else. This pins the
    producer's routing to the SSoT by behavior (no source coupling needed)."""
    filename, header = IMPACT_TARGETS[impact]
    proj = tmp_path / "proj"
    # Seed BOTH docs so a mis-route would still find a writable target.
    _seed_doc(proj, "architecture.md", "## Architecture Updates")
    _seed_doc(proj, "conventions.md", "## Convention Updates")

    target = write_decision_log._append_architecture_update(proj, 7, impact, "summary")
    assert target == filename

    doc = proj / ".shipwright" / "agent_docs"
    assert "ADR-007" in (doc / filename).read_text(encoding="utf-8")
    other = "conventions.md" if filename == "architecture.md" else "architecture.md"
    assert "ADR-007" not in (doc / other).read_text(encoding="utf-8")


def test_writer_ignores_none_impact(tmp_path: Path):
    proj = tmp_path / "proj"
    _seed_doc(proj, "architecture.md", "## Architecture Updates")
    assert write_decision_log._append_architecture_update(proj, 7, "none", "x") is None


# --- routing SSoT: F2.md instruction matches IMPACT_TARGETS ------------------


def _f2_text() -> str:
    f2 = (
        _REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
        / "references" / "F2.md"
    )
    return f2.read_text(encoding="utf-8", errors="ignore")


def test_f2_documents_canonical_routing():
    """F2.md must name each impact's canonical target section so the agent
    hand-appends to the same place the producer + oracle expect."""
    text = _f2_text()
    # convention → conventions.md ## Convention Updates
    assert "## Convention Updates" in text
    assert "conventions.md" in text
    # component / data-flow → architecture.md ## Architecture Updates
    assert "## Architecture Updates" in text
    assert "architecture.md" in text
