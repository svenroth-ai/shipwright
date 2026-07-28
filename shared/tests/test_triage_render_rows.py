"""What a rendered triage row promises, and what it must not.

iterate-2026-07-27-triage-defer-review-followup — the Stage-2 `code-reviewer`
and Stage-3 `doubt-reviewer` passes on the merged PR #444 found four render
defects the three external rounds had missed. Each one is pinned here.

Kept out of `test_triage_defer.py` (292 lines): appending would cross the
300-line budget.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.triage_render import (  # noqa: E402
    DEFERRED_MARK,
    OPEN_MARK,
    FIELD_MAX_LEN,
    NO_REASON,
    format_deferred,
    format_item,
)
from triage import append_triage_item, mark_status  # noqa: E402

TRIAGE_CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"


def _cli(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TRIAGE_CLI), "--project-root", str(project), *args],
        capture_output=True, text=True, check=False,
    )


def _deferred(**over) -> dict:
    item = {
        "id": "trg-abc12345", "severity": "medium", "kind": "bug",
        "source": "manual", "title": "a title", "statusReason": "later",
        "status": "snoozed",
    }
    item.update(over)
    return item


# ---------------------------------------------------------------------------
# AC-1 — an empty reason reads the same as an absent one
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stored", [None, "", "   ", "\t", "\n", "  \t \n "])
def test_a_reason_that_renders_to_nothing_says_so(stored) -> None:
    """The fallback runs AFTER sanitising.

    `"   "` is truthy, so applying the fallback first left a blank `reason:`
    line — and the previous run's test happened to pick `None`, the one falsy
    input for which the wrong order still works.
    """
    rendered = format_deferred(_deferred(statusReason=stored))
    assert f"  reason: {NO_REASON}" in rendered
    assert "  reason: \n" not in rendered


def test_a_real_reason_is_still_printed() -> None:
    assert "  reason: waiting on upstream" in format_deferred(
        _deferred(statusReason="waiting on upstream")
    )


# ---------------------------------------------------------------------------
# AC-2 — the ROW carries the distinction, not just the section header
# ---------------------------------------------------------------------------

def test_a_deferred_row_is_marked_as_deferred() -> None:
    assert format_deferred(_deferred()).startswith(f"- {DEFERRED_MARK}trg-")


def test_an_open_row_is_marked_open() -> None:
    open_item = {"id": "trg-open0001", "severity": "low", "kind": "bug",
                 "source": "manual", "title": "t"}
    assert format_item(open_item).startswith(f"- {OPEN_MARK}trg-")


def test_a_forged_marker_in_an_untrusted_field_cannot_reclassify_a_row() -> None:
    """`source` is free-form and `dedupKey` is built from a workflow name."""
    forger = {"id": "trg-open0001", "severity": "low", "kind": "bug",
              "source": f"{DEFERRED_MARK}github", "title": "t",
              "dedupKey": f"gh-ci:{DEFERRED_MARK}x"}
    row = format_item(forger).splitlines()[0]
    assert DEFERRED_MARK in row                       # the text is still shown
    assert row.startswith(f"- {OPEN_MARK}")           # but it is still OPEN
    assert not row.startswith(f"- {DEFERRED_MARK}")


def test_the_listing_never_repeats_a_row_shape_across_the_two_meanings(
    tmp_path: Path,
) -> None:
    """Each entry row declares which of the two it is, by prefix.

    Before the deferred section existed, `- trg-` at column 0 meant "open" for
    free. No row starts that way any more: both kinds carry an explicit token,
    so the distinction is a property of the row rather than of a header printed
    once above it.
    """
    open_id = append_triage_item(
        tmp_path, source="manual", severity="low", kind="bug",
        title="still open", detail="d",
    )
    parked_id = append_triage_item(
        tmp_path, source="manual", severity="low", kind="bug",
        title="parked", detail="d",
    )
    mark_status(tmp_path, parked_id, new_status="snoozed", by="cli",
                reason="later")
    out = _cli(tmp_path, "list").stdout

    rows = [ln for ln in out.splitlines() if ln.startswith("- ")]
    assert len(rows) == 2
    # Classified by PREFIX. A `DEFERRED_MARK in row` search would be forgeable
    # by an open entry whose `source` or `dedupKey` contains the token — both
    # come from the code host and are attacker-influenceable.
    opened = [r for r in rows if r.startswith(f"- {OPEN_MARK}")]
    parked = [r for r in rows if r.startswith(f"- {DEFERRED_MARK}")]
    assert len(opened) == 1 and open_id in opened[0]
    assert len(parked) == 1 and parked_id in parked[0]


# ---------------------------------------------------------------------------
# AC-3 — the compact block is capped, like every other capped surface
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["title", "statusReason", "source"])
def test_a_deferred_field_cannot_grow_without_limit(field: str) -> None:
    """The Command Center stores a reason with no length validation at all, so
    the render side is the only place this is bounded today.

    Asserted on the FIELD, not the line: `source` shares its line with the id,
    severity and kind labels, so a whole-line budget would need a fudge factor
    and would stop measuring the thing that is capped.
    """
    rendered = format_deferred(_deferred(**{field: "x" * 5000}))
    # Pins the longest filler run at exactly FIELD_MAX_LEN - 1: the cap keeps
    # one slot for the ellipsis. No cap gives 5000; an off-by-one gives 120.
    assert "x" * (FIELD_MAX_LEN - 1) in rendered
    assert "x" * FIELD_MAX_LEN not in rendered
    assert "…" in rendered


@pytest.mark.parametrize(
    "length,expect_clipped",
    [(FIELD_MAX_LEN - 1, False), (FIELD_MAX_LEN, False), (FIELD_MAX_LEN + 1, True)],
)
def test_only_what_exceeds_the_cap_is_clipped(length, expect_clipped) -> None:
    rendered = format_deferred(_deferred(title="t" * length))
    assert ("…" in rendered) is expect_clipped


# ---------------------------------------------------------------------------
# AC-4 — the STORED value decides the branch, the sanitized one is printed
# ---------------------------------------------------------------------------

def test_a_dedup_key_of_only_control_characters_is_still_emitted() -> None:
    """It sanitises to "", so a display-massaged predicate would drop the field
    entirely — the same class as the `source` fix, at a second site."""
    open_item = {"id": "trg-open0001", "severity": "low", "kind": "bug",
                 "source": "manual", "title": "t", "dedupKey": "\x1b\x07"}
    header = format_item(open_item).splitlines()[0]
    assert "dedupKey=" in header
    assert "\x1b" not in header and "\x07" not in header


def test_an_absent_dedup_key_is_still_omitted() -> None:
    open_item = {"id": "trg-open0001", "severity": "low", "kind": "bug",
                 "source": "manual", "title": "t"}
    assert "dedupKey=" not in format_item(open_item)


# ---------------------------------------------------------------------------
# AC-6 — the help text matches what `list` prints
# ---------------------------------------------------------------------------

def test_the_list_help_mentions_the_deferred_section(tmp_path: Path) -> None:
    """`--help` is the surface an operator actually reads, and `list` stopped
    printing only open items."""
    out = _cli(tmp_path, "--help").stdout
    assert "deferred" in out.lower()
