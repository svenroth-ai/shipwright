"""Entry-budget + routing-SSoT guards for the always-loaded agent docs.

Two structural guards that keep the Layer-1 agent docs lean and consistently
routed (the agent-doc-entry-rules split, 2026-06-12; hole-closed +
SSoT-extracted, 2026-06-14). They make the progressive-disclosure rule
enforceable rather than advisory:

1. ENTRY BUDGET (forward-only). Each DATED entry under ``## Architecture
   Updates`` (architecture.md) and ``## Convention Updates`` / ``## Learnings``
   (conventions.md) authored on/after ``_ENFORCED_FROM`` must be
   ``<= ENTRY_MAX_CHARS``. Detail belongs ONCE in the on-demand ADR /
   ``.shipwright/planning/adr/`` spec folder; the always-loaded docs carry a
   one-line "what + pointer". Mirrors the per-field budget already enforced on
   ``decision_log.md`` (``write_decision_log.ADR_FIELD_MAX_CHARS``).

   The parsing + budget logic is the shared SSoT ``lib.agent_doc_budget`` (also
   consumed by the repo-agnostic CLI ``tools/check_agent_doc_budget.py`` and the
   F11 verifier), so the monorepo gate and the adopted-repo runtime gate cannot
   diverge. ``entry_date`` reads the date from a bare ``(YYYY-MM-DD)`` OR a
   run-id slug ``(iterate-YYYY-MM-DD-…)``, closing the hole that used to exempt
   the bold ``- **rule** (iterate-…-slug)`` Learnings form. Genuinely undated
   entries (no parenthesised date) remain grandfathered.

2. ROUTING SSoT. The impact -> (target doc, section) mapping is defined once in
   ``lib.architecture_doc.IMPACT_TARGETS`` and consumed by the oracle (F11 gate
   + Group-F detective), the producer (``write_decision_log``), and the F2.md
   instruction. These tests pin producer + instruction to the SSoT so the three
   cannot silently diverge again.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "tools"))

import write_decision_log  # noqa: E402
from lib.agent_doc_budget import (  # noqa: E402
    ENTRY_MAX_CHARS,
    SECTIONS,
    iter_entries,
    over_budget,
)
from lib.agent_doc_shape import ENFORCED_FROM as _SHAPE_ENFORCED_FROM  # noqa: E402
from lib.agent_doc_shape import SHAPE_SECTIONS, non_canonical  # noqa: E402
from lib.architecture_doc import IMPACT_TARGETS, REAL_IMPACTS  # noqa: E402

# Enforcement boundary: every entry authored on/after this date must comply.
# 2026-05-01 sits just before the earliest dated backlog entry (2026-05-02), so
# the gate enforces the entire compacted corpus rather than only forward-dated
# entries. Genuinely undated entries (no parenthesised date) remain exempt.
_ENFORCED_FROM = date(2026, 5, 1)

_AGENT_DOCS = _REPO_ROOT / ".shipwright" / "agent_docs"


# --- entry budget (real files) ----------------------------------------------


@pytest.mark.parametrize("filename,header", SECTIONS)
def test_new_entries_within_budget(filename: str, header: str):
    """Every entry authored on/after _ENFORCED_FROM is a one-line pointer
    (<= ENTRY_MAX_CHARS). Genuinely undated legacy entries are exempt."""
    path = _AGENT_DOCS / filename
    if not path.exists():
        pytest.skip(f"{filename} absent")  # test-hygiene: allow-silent-skip: defensive guard for partial/non-repo checkout; file is present in CI
    entries = iter_entries(path.read_text(encoding="utf-8", errors="ignore"), header)
    violations = over_budget(entries, enforced_from=_ENFORCED_FROM)
    if violations:
        pytest.fail(
            f"{filename} '{header}' has over-budget entries authored on/after "
            f"{_ENFORCED_FROM.isoformat()} — keep each entry a one-line 'what + "
            f"ADR pointer'; move detail into the ADR / .shipwright/planning/adr/ "
            "spec folder (see references/F2.md, references/reflection.md):\n  - "
            + "\n  - ".join(violations)
        )


# --- entry shape (real files) -----------------------------------------------


@pytest.mark.parametrize("filename,header", SHAPE_SECTIONS)
def test_dated_entries_are_canonical_shape(filename: str, header: str):
    """Every dated changelog bullet on/after the shape cutoff is
    ``- **<run_id|ADR-NNN>** (date): <Impact> — <sentence>. → <pointer>``.
    Locks the one-time normalization so a non-canonical entry (a Campaign /
    sub_iterate / free-text anchor, a duplicate ADR-NNN dup, or a missing arrow)
    can't creep back into the monorepo docs. ``## Learnings`` is intentionally NOT
    in SHAPE_SECTIONS (date-first grammar). The F11 verifier covers the
    forward-only adopted-repo path."""
    path = _AGENT_DOCS / filename
    if not path.exists():
        pytest.skip(f"{filename} absent")
    entries = iter_entries(path.read_text(encoding="utf-8", errors="ignore"), header)
    violations = non_canonical(entries, enforced_from=_SHAPE_ENFORCED_FROM)
    if violations:
        pytest.fail(
            f"{filename} '{header}' has non-canonical dated entries on/after "
            f"{_SHAPE_ENFORCED_FROM.isoformat()} — each must read "
            "'- **<run_id|ADR-NNN>** (YYYY-MM-DD): <Impact> — <sentence>. → <pointer>' "
            "(no Campaign/sub_iterate/free-text anchor; see references/F2.md):\n  - "
            + "\n  - ".join(violations)
        )


# --- entry budget (hermetic — proves the gate discriminates) ----------------


def test_over_budget_dated_entry_is_flagged():
    after = (_ENFORCED_FROM + timedelta(days=1)).isoformat()
    big = f"- **x** ({after}): " + ("y" * (ENTRY_MAX_CHARS + 50))
    assert over_budget([big], enforced_from=_ENFORCED_FROM)


def test_slug_dated_entry_is_no_longer_exempt():
    """Regression for the closed hole: a bold-lead entry whose only date is in
    the run-id slug used to parse as undated (exempt). It must now be enforced."""
    big = "- **" + ("y" * (ENTRY_MAX_CHARS + 50)) + "** (iterate-2026-06-13-foo)"
    assert over_budget([big], enforced_from=_ENFORCED_FROM)


def test_grandfathered_entries_exempt():
    # A pre-cutoff dated entry and a genuinely undated entry stay exempt.
    before = (_ENFORCED_FROM - timedelta(days=1)).isoformat()
    big_old = f"- **x** ({before}): " + ("y" * (ENTRY_MAX_CHARS + 50))
    big_undated = "- **x**: " + ("y" * (ENTRY_MAX_CHARS + 50))
    assert over_budget([big_old], enforced_from=_ENFORCED_FROM) == []
    assert over_budget([big_undated], enforced_from=_ENFORCED_FROM) == []


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
