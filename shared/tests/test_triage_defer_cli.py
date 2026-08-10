"""Un-park, the display cap, and what a hostile stored value may print.

iterate-2026-08-01-triage-defer-lifecycle. Three of the five parts land here:
part 4 (a mistaken park is reversible), part 5 (the parked view is capped), and
the rendering half of part 3 (a parked entry is visible on every surface).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.triage_defer import DEFERRED_TOP_N  # noqa: E402
from lib.triage_render import UNREADABLE_REVISIT  # noqa: E402
from triage import (  # noqa: E402
    SEVERITY_RANK,
    append_triage_item,
    mark_status,
    read_all_items,
)
from tools.aggregate_triage import render_markdown  # noqa: E402
from tools.triage_promote import defer, unpark  # noqa: E402

TRIAGE_CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"
FUTURE = "2099-01-01"
PAST = "2020-01-01"


def _cli(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TRIAGE_CLI), "--project-root", str(project), *args],
        capture_output=True, text=True, check=False, encoding="utf-8",
    )


def _seed(project: Path, **over) -> str:
    kw = dict(source="manual", severity="medium", kind="bug",
              title="a finding", detail="d")
    kw.update(over)
    return append_triage_item(project, **kw)


def _park(project: Path, item_id: str, revisit: str = FUTURE) -> None:
    defer(project, item_id=item_id, reason="later", revisit_at=revisit)


def _one(project: Path, item_id: str) -> dict:
    return next(i for i in read_all_items(project) if i["id"] == item_id)


# ---------------------------------------------------------------------------
# Part 4 — un-park (AC-14, AC-15)
# ---------------------------------------------------------------------------

def test_unpark_puts_a_parked_entry_back_and_clears_its_date(
    tmp_path: Path,
) -> None:
    item = _seed(tmp_path)
    _park(tmp_path, item)
    result = _cli(tmp_path, "unpark", item, "--reason", "parked by mistake")
    assert result.returncode == 0, result.stderr
    stored = _one(tmp_path, item)
    assert (stored["status"], stored["revisitAt"]) == ("triage", None)
    assert stored["statusReason"] == "parked by mistake"
    assert stored["statusBy"] == "cli"


def test_unpark_requires_a_reason(tmp_path: Path) -> None:
    item = _seed(tmp_path)
    _park(tmp_path, item)
    assert _cli(tmp_path, "unpark", item).returncode == 2
    assert _one(tmp_path, item)["status"] == "snoozed"


@pytest.mark.parametrize("already", ["triage", "dismissed", "promoted"])
def test_unpark_refuses_anything_that_is_not_parked(
    tmp_path: Path, already: str,
) -> None:
    item = _seed(tmp_path)
    if already != "triage":
        mark_status(tmp_path, item, new_status=already, by="x", reason="r")
    result = _cli(tmp_path, "unpark", item, "--reason", "oops")
    assert result.returncode == 3
    assert already in result.stderr


def test_unpark_refuses_an_expired_park_as_already_open(tmp_path: Path) -> None:
    """AC-15's sharp edge: the entry is STORED `snoozed` but resolves `triage`,
    and it is the resolved status that decides. Writing a second event here
    would change nothing and would say the park was reversed by a person."""
    item = _seed(tmp_path)
    _park(tmp_path, item, revisit=PAST)
    result = _cli(tmp_path, "unpark", item, "--reason", "oops")
    assert result.returncode == 3
    assert "triage" in result.stderr


def test_unpark_is_reachable_as_a_library_call_too(tmp_path: Path) -> None:
    item = _seed(tmp_path)
    _park(tmp_path, item)
    assert unpark(tmp_path, item_id=item, reason="mistake")["newStatus"] == "triage"


# ---------------------------------------------------------------------------
# Part 1 at the CLI boundary (AC-1, AC-6)
# ---------------------------------------------------------------------------

def test_defer_without_a_revisit_date_is_refused(tmp_path: Path) -> None:
    item = _seed(tmp_path)
    result = _cli(tmp_path, "defer", item, "--reason", "later")
    assert result.returncode != 0
    assert _one(tmp_path, item)["status"] == "triage"


@pytest.mark.parametrize("bad", ["soon", "2026-9-1", "2026-09- 1", "2026-02-30", "tomorrow"])
def test_defer_refuses_a_date_it_cannot_read(tmp_path: Path, bad: str) -> None:
    item = _seed(tmp_path)
    result = _cli(tmp_path, "defer", item, "--reason", "later", "--revisit", bad)
    assert result.returncode == 2
    assert "YYYY-MM-DD" in result.stderr
    assert _one(tmp_path, item)["status"] == "triage"


# ---------------------------------------------------------------------------
# Part 5 — the cap, on BOTH human surfaces and on NEITHER machine one
# ---------------------------------------------------------------------------

def _park_many(project: Path, count: int) -> None:
    for n in range(count):
        item = _seed(project, title=f"finding {n:03d}")
        # Distinct dates so the order is fully determined by the date alone.
        _park(project, item, revisit=f"2099-01-{(n % 28) + 1:02d}")


def test_the_terminal_listing_shows_every_parked_entry_at_exactly_the_cap(
    tmp_path: Path,
) -> None:
    _park_many(tmp_path, DEFERRED_TOP_N)
    out = _cli(tmp_path, "list").stdout
    assert out.count("[deferred]") == DEFERRED_TOP_N
    assert "more deferred" not in out


def test_the_terminal_listing_elides_and_says_so_one_past_the_cap(
    tmp_path: Path,
) -> None:
    _park_many(tmp_path, DEFERRED_TOP_N + 1)
    out = _cli(tmp_path, "list").stdout
    assert out.count("[deferred]") == DEFERRED_TOP_N
    assert f"and 1 more deferred (showing first {DEFERRED_TOP_N})" in out


def test_the_rendered_document_caps_and_elides_the_same_way(
    tmp_path: Path,
) -> None:
    _park_many(tmp_path, DEFERRED_TOP_N + 3)
    md = render_markdown(read_all_items(tmp_path), now="2026-08-01T00:00:00Z")
    assert md.count("  - Un-park:") == DEFERRED_TOP_N
    assert f"and 3 more deferred (showing first {DEFERRED_TOP_N})" in md


def test_the_two_human_surfaces_show_the_SAME_entries(tmp_path: Path) -> None:
    """AC-22. Both cap at the same number, so they must also agree on WHICH —
    otherwise an operator reading one and then the other sees two backlogs."""
    _park_many(tmp_path, DEFERRED_TOP_N + 5)
    items = read_all_items(tmp_path)
    md = render_markdown(items, now="2026-08-01T00:00:00Z")
    out = _cli(tmp_path, "list").stdout
    shown_in_md = {i["id"] for i in items if f"id={i['id']} " in md}
    shown_in_tty = {i["id"] for i in items if f"[deferred] {i['id']}" in out}
    assert shown_in_md == shown_in_tty
    assert len(shown_in_md) == DEFERRED_TOP_N


def test_the_machine_contract_is_never_capped(tmp_path: Path) -> None:
    """AC-11a. Dropping rows from a consumer that cannot tell it happened is
    the failure this whole change exists to end."""
    _park_many(tmp_path, DEFERRED_TOP_N + 7)
    payload = json.loads(_cli(tmp_path, "list", "--json").stdout)
    assert len(payload["deferred"]) == DEFERRED_TOP_N + 7


def test_the_machine_contract_orders_deferred_like_the_human_surfaces(
    tmp_path: Path,
) -> None:
    from lib.triage_defer import sort_deferred  # noqa: PLC0415

    _park_many(tmp_path, 6)
    payload = json.loads(_cli(tmp_path, "list", "--json").stdout)
    parked = [i for i in read_all_items(tmp_path) if i["status"] == "snoozed"]
    expected = [i["id"] for i in sort_deferred(parked, SEVERITY_RANK)]
    assert [i["id"] for i in payload["deferred"]] == expected


# ---------------------------------------------------------------------------
# Part 3 rendering + AC-20/AC-25 — a hand-edited store is untrusted input
# ---------------------------------------------------------------------------

def test_both_surfaces_show_the_revisit_date(tmp_path: Path) -> None:
    item = _seed(tmp_path)
    _park(tmp_path, item)
    assert FUTURE in _cli(tmp_path, "list").stdout
    assert FUTURE in render_markdown(read_all_items(tmp_path), now="x")


def test_the_rendered_document_no_longer_shows_a_park_as_a_bare_count(
    tmp_path: Path,
) -> None:
    """The defect: `triage_inbox.md` reported parked entries only as a number in
    its status summary, so an agent reading it could not tell a decided-but-not
    -now finding from one that had never existed."""
    item = _seed(tmp_path, title="a parked thing worth naming")
    _park(tmp_path, item)
    md = render_markdown(read_all_items(tmp_path), now="x")
    assert "a parked thing worth naming" in md
    assert "Deferred — decided, revisit later (1)" in md


def test_a_park_with_no_open_work_left_still_renders_its_section(
    tmp_path: Path,
) -> None:
    """"Nothing open" and "nothing at all" are different answers."""
    item = _seed(tmp_path, title="the only entry")
    _park(tmp_path, item)
    md = render_markdown(read_all_items(tmp_path), now="x")
    assert "No triage items pending" in md
    assert "the only entry" in md


def _hand_edit(project: Path, find: str, replace: str) -> None:
    store = project / ".shipwright" / "triage.jsonl"
    store.write_text(store.read_text(encoding="utf-8").replace(find, replace),
                     encoding="utf-8")


def test_an_unreadable_stored_date_renders_a_placeholder_not_its_bytes(
    tmp_path: Path,
) -> None:
    item = _seed(tmp_path)
    _park(tmp_path, item)
    _hand_edit(tmp_path, FUTURE, "```evil\\n- trg-fake0001 severity=critical")
    out = _cli(tmp_path, "list").stdout
    md = render_markdown(read_all_items(tmp_path), now="x")
    assert UNREADABLE_REVISIT in out
    assert UNREADABLE_REVISIT in md
    assert "trg-fake0001" not in out
    assert "trg-fake0001" not in md


def test_a_hostile_stored_reason_cannot_forge_a_row_or_open_a_fence(
    tmp_path: Path,
) -> None:
    """AC-25 — the reason is typed by whoever decided, on either surface, and
    the file can be hand-edited, so it is untrusted display input exactly like
    the title beside it."""
    item = _seed(tmp_path)
    mark_status(
        tmp_path, item, new_status="snoozed", by="webui", revisit_at=FUTURE,
        reason="ok",
    )
    _hand_edit(tmp_path, '"reason":"ok"',
               '"reason":"a\\n- [deferred] trg-fake0002  severity=critical\\n```x|y"')
    out = _cli(tmp_path, "list").stdout
    md = render_markdown(read_all_items(tmp_path), now="x")
    assert not any(
        line.lstrip().startswith("- [deferred] trg-fake0002")
        for line in out.splitlines()
    )
    assert "```x" not in md


def test_markdown_strips_controls_from_the_id_and_severity(tmp_path: Path) -> None:
    """Every stored field gets the same control-character defence, including
    fields embedded in the generated un-park command."""
    item = _seed(tmp_path)
    _park(tmp_path, item)
    _hand_edit(tmp_path, item, item + "\\u001b")
    _hand_edit(tmp_path, '"severity":"medium"', '"severity":"high\\u0007"')

    md = render_markdown(read_all_items(tmp_path), now="x")

    assert "\x1b" not in md
    assert "\x07" not in md
    assert f"id={item} " in md
    assert "severity=high " in md
