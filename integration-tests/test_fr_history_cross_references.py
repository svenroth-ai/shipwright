"""No dead pointers in the S7 machinery (campaign S7).

A docstring citing ``test_fr_change_history_amendment_parity`` — a test that did
not exist — is what set this strand off. The fix for it shipped with a second
instance: a comment naming a check that had been renamed. Two instances of one
class, so the class gets a check rather than each instance getting a correction.

Scoped to the files this campaign step added or edited, because a repo-wide
version would be a different (and much noisier) piece of work.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

#: A name cited precisely BECAUSE it never existed is the subject matter of the
#: records above, not a defect. Mirrors the retraction-marker allowance in
#: ``_fr_history_docs`` — without it, recording the dead-pointer defect would
#: itself trip the dead-pointer check.
_ABSENT_BY_DESIGN_MARKERS = (
    "did not exist", "nonexistent", "never created", "never existed",
    "also nonexistent", "had been renamed", "dead pointer",
)

# --------------------------------------------------------------------------
# Cross-references
# --------------------------------------------------------------------------

#: Where this campaign step put code, and the filename rule that identifies it.
#: DERIVED, never hand-listed — deliberately the same rule as
#: ``test_fr_history_display_lists.s7_sources``, because two hand-maintained
#: copies of "the S7 files" had already drifted apart after a single round, each
#: missing a module the other had. The accessor below is ``_prose_sources()``,
#: not a second ``_S7_SOURCES``: these two checks scan overlapping but
#: *different* sets — this one also reads the ADR, which has no display lists to
#: inspect — and identical names invited exactly the mistake that was made.
_CODE_ROOTS = (
    "shared/scripts/lib",
    "shared/scripts/tools",
    "shared/scripts/tests",
    "integration-tests",
)
_NAME_MARKERS = ("fr_history", "fr_change_history")

#: Prose that is not code but cites test names as evidence.
_PROSE_DOCUMENTS = (
    ".shipwright/planning/adr/110-change-history-as-a-derived-view.md",
)

_SEARCH_ROOTS = ("integration-tests", "shared/scripts/tests", "shared/tests")


def _prose_sources() -> list[str]:
    """Every S7 file whose prose may cite a test name, repo-relative."""
    found = [
        f"{root}/{path.name}"
        for root in _CODE_ROOTS
        for path in sorted((_REPO / root).glob("*.py"))
        if any(marker in path.name for marker in _NAME_MARKERS)
    ]
    return found + list(_PROSE_DOCUMENTS)


def test_every_test_name_cited_in_prose_actually_exists():
    """No dead pointers inside the anti-dead-pointer machinery.

    A docstring citing ``test_fr_change_history_amendment_parity`` — a test that
    did not exist — is what set this whole strand off. The fix for that shipped
    with a second one: a comment naming
    ``test_the_shipped_documents_quote_the_published_counts``, also nonexistent.
    Two instances of one class, so the class gets the check rather than each
    instance getting a correction.
    """
    defined: set[str] = set()
    for root in _SEARCH_ROOTS:
        for path in (_REPO / root).rglob("*.py"):
            defined.update(re.findall(r"^def (test_\w+)", path.read_text(
                encoding="utf-8", errors="replace"), flags=re.MULTILINE))
    assert defined, "no test functions discovered — the search roots are wrong"

    modules = {p.stem for root in _SEARCH_ROOTS
               for p in (_REPO / root).rglob("*.py")}

    dangling: dict[str, list[str]] = {}
    for rel in _prose_sources():
        path = _REPO / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        missing: list[str] = []
        for match in re.finditer(r"(?<![\w.])test_\w+", text):
            name = match.group(0)
            if name in defined or name in modules:
                continue
            # A name cited precisely BECAUSE it never existed is the subject
            # matter here, not a defect — the same allowance the retraction
            # detector makes. Without it, recording the dead-pointer defect
            # would itself trip the dead-pointer check.
            window = text[max(0, match.start() - 250):match.end() + 250].lower()
            if any(m in window for m in _ABSENT_BY_DESIGN_MARKERS):
                continue
            missing.append(name)
        if missing:
            dangling[rel] = sorted(set(missing))

    assert not dangling, (
        f"prose cites test name(s) that are defined nowhere: {dangling}. "
        f"Either the test was renamed and the reference not updated, or the "
        f"reference was written for a test that was never created."
    )


def test_the_prose_source_set_is_discovered_and_not_hand_listed():
    """A glob that silently matched nothing would make the check vacuous.

    Also asserts the two derived sets agree on the code files. They are allowed
    to differ only by the ADR, which carries prose but no display lists — any
    other divergence means one guard has stopped covering a module the other
    still does, which is the drift this replaced.
    """
    sources = _prose_sources()
    assert len(sources) >= 16, f"only {len(sources)} prose sources: {sources}"

    for anchor in (
        "shared/scripts/lib/fr_change_history.py",
        "shared/scripts/lib/fr_history_render.py",
        "shared/scripts/tools/fr_history.py",
        "integration-tests/test_fr_history_cross_references.py",
        ".shipwright/planning/adr/110-change-history-as-a-derived-view.md",
    ):
        assert anchor in sources, f"{anchor} is not covered by the discovery rule"

    code = {s for s in sources if s.endswith(".py")}
    extra = set(sources) - code
    assert extra == set(_PROSE_DOCUMENTS), (
        f"non-code entries drifted from the documented list: {sorted(extra)}"
    )
