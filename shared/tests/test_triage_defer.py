"""The third triage decision — *defer* — on the terminal surface.

iterate-2026-07-27-triage-defer-ci-cap, card ``trg-813d2305`` (REQ-3 Phase 2
walk of FR-01.14, criterion 2). ``snoozed`` was a real status the Command
Center wrote and the CLI could not, so an operator working from the terminal
could make only two of the three decisions the requirement promises.

Deliberately a NEW file rather than an addition to ``test_triage_cli.py`` /
``test_triage_promote.py``: the first sits at the 300-line budget and the
second is baselined at 375, so appending to either would ratchet the bloat
baseline (`shared/glossary.md` → Anti-Ratchet).
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

from triage import (  # noqa: E402
    TRIAGE_FILE,
    append_triage_item,
    mark_status,
    read_all_items,
)
from tools import triage_promote  # noqa: E402
from tools.triage_promote import defer, dismiss  # noqa: E402

TRIAGE_CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"

#: Far enough out that no run of this suite can straddle it, so "parked" here
#: always means "parked and not yet due" (iterate-2026-08-01-triage-defer-
#: lifecycle made a park time-bounded; before it, a park had no date at all).
FUTURE = "2099-01-01"


def _cli(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TRIAGE_CLI), "--project-root", str(project), *args],
        capture_output=True, text=True, check=False,
    )


def _store(project: Path) -> str:
    return (project / ".shipwright" / TRIAGE_FILE).read_text(encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def item(project: Path) -> str:
    return append_triage_item(
        project, source="phaseQuality", severity="high", kind="bug",
        title="Phase-Quality C1 failure", detail="some context",
    )


def _only(project: Path) -> dict:
    [resolved] = read_all_items(project)
    return resolved


# ---------------------------------------------------------------------------
# AC-1..AC-4 — the shared library helper
# ---------------------------------------------------------------------------

def test_defer_records_the_decision_and_its_reason(project: Path, item: str) -> None:
    result = defer(project, item_id=item, reason="waiting on upstream fix",
                   revisit_at=FUTURE)
    assert result == {
        "id": item, "previousStatus": "triage",
        "newStatus": "snoozed", "reason": "waiting on upstream fix",
        "revisitAt": FUTURE,
    }
    stored = _only(project)
    assert stored["status"] == "snoozed"
    assert stored["statusReason"] == "waiting on upstream fix"
    assert stored["statusBy"] == "manualDefer"


@pytest.mark.parametrize("reason", ["", "   ", "\t"])
def test_defer_refuses_a_reason_that_says_nothing(
    project: Path, item: str, reason: str,
) -> None:
    """A deferral without a stated reason is not a decision (AC-2)."""
    before = _store(project)
    with pytest.raises(ValueError):
        defer(project, item_id=item, reason=reason, revisit_at=FUTURE)
    assert _store(project) == before


def test_defer_helper_refuses_a_missing_revisit_date_without_writing(
    project: Path, item: str,
) -> None:
    before = _store(project)
    with pytest.raises(ValueError, match="revisit_at is required"):
        defer(project, item_id=item, reason="later", revisit_at=None)  # type: ignore[arg-type]
    assert _store(project) == before


def test_defer_refuses_control_characters_in_the_reason(
    project: Path, item: str,
) -> None:
    with pytest.raises(ValueError, match="control character"):
        defer(project, item_id=item, reason="park\x1b]2;evil\x07it",
              revisit_at=FUTURE)


@pytest.mark.parametrize("already", ["dismissed", "promoted"])
def test_defer_refuses_an_item_whose_life_already_ended(
    project: Path, item: str, already: str,
) -> None:
    """Asserted on the stored BYTES, not the resolved status — a status
    assertion could pass for a guard that had been removed.

    ``snoozed`` left this list in iterate-2026-08-01-triage-defer-lifecycle:
    re-parking is now a supported correction, covered by the test below.
    """
    mark_status(project, item, new_status=already, by="x", reason="r")
    before = _store(project)
    with pytest.raises(ValueError, match="only `triage` or `snoozed` is"):
        defer(project, item_id=item, reason="later", revisit_at=FUTURE)
    assert _store(project) == before


def test_defer_accepts_an_already_parked_item_and_replaces_the_date(
    project: Path, item: str,
) -> None:
    """A mistyped revisit date must be correctable without un-parking first."""
    defer(project, item_id=item, reason="later", revisit_at="2098-01-01")
    result = defer(project, item_id=item, reason="later still",
                   revisit_at=FUTURE)
    assert result["previousStatus"] == "snoozed"
    assert _only(project)["revisitAt"] == FUTURE


def test_defer_reports_the_status_it_replaced_inside_the_lock(
    project: Path, item: str, monkeypatch,
) -> None:
    """A concurrent re-park is allowed, so the unlocked status may be stale."""
    real_mark_status = triage_promote.mark_status
    fired = False

    def park_then_write(*args, **kwargs):
        nonlocal fired
        if not fired:
            fired = True
            mark_status(project, item, new_status="snoozed", by="other",
                        reason="other park", revisit_at="2098-01-01")
        return real_mark_status(*args, **kwargs)

    monkeypatch.setattr(triage_promote, "mark_status", park_then_write)
    result = defer(project, item_id=item, reason="mine", revisit_at=FUTURE)
    assert result["previousStatus"] == "snoozed"


def test_defer_unknown_id_raises_key_error(project: Path, item: str) -> None:
    with pytest.raises(KeyError):
        defer(project, item_id="trg-deadbeef", reason="later",
              revisit_at=FUTURE)


def test_defer_without_a_store_raises_file_not_found(project: Path) -> None:
    with pytest.raises(FileNotFoundError):
        defer(project, item_id="trg-deadbeef", reason="later",
              revisit_at=FUTURE)


def test_dismiss_is_unchanged_by_the_shared_extraction(
    project: Path, item: str,
) -> None:
    """Regression net for the `dismiss`/`defer` common body (plan review #3)."""
    result = dismiss(project, item_id=item, reason="not relevant")
    assert result == {
        "id": item, "previousStatus": "triage",
        "newStatus": "dismissed", "reason": "not relevant",
    }
    stored = _only(project)
    assert (stored["status"], stored["statusBy"]) == ("dismissed", "manualDismiss")


# ---------------------------------------------------------------------------
# AC-1..AC-3 — the CLI subcommand
# ---------------------------------------------------------------------------

def test_cli_defer_records_the_operator_as_the_actor(
    project: Path, item: str,
) -> None:
    result = _cli(project, "defer", item, "--reason", "revisit after v0.5",
                 "--revisit", FUTURE)
    assert result.returncode == 0, result.stderr
    stored = _only(project)
    assert stored["status"] == "snoozed"
    assert stored["statusReason"] == "revisit after v0.5"
    assert stored["statusBy"] == "cli"
    assert "deferred" in result.stderr


@pytest.mark.parametrize(
    "extra", [[], ["--reason", "  ", "--revisit", FUTURE],
              ["--reason", "real reason"]],
    ids=["nothing", "blank-reason", "no-revisit-date"],
)
def test_cli_defer_refuses_and_writes_nothing_without_a_real_reason(
    project: Path, item: str, extra: list[str],
) -> None:
    before = _store(project)
    result = _cli(project, "defer", item, *extra)
    assert result.returncode == 2
    assert _store(project) == before


@pytest.mark.parametrize("verb", ["defer", "dismiss"])
def test_cli_leaves_the_store_untouched_when_it_refuses(
    project: Path, item: str, verb: str,
) -> None:
    """Both decisions reject an unknown id the same way (plan review #11)."""
    before = _store(project)
    extra = ["--revisit", FUTURE] if verb == "defer" else []
    result = _cli(project, verb, "trg-deadbeef", "--reason", "later", *extra)
    assert result.returncode == 4
    assert "not found" in result.stderr.lower()
    assert _store(project) == before


def test_cli_defer_refuses_an_already_decided_item(
    project: Path, item: str,
) -> None:
    mark_status(project, item, new_status="dismissed", by="x", reason="r")
    before = _store(project)
    result = _cli(project, "defer", item, "--reason", "later",
                     "--revisit", FUTURE)
    assert result.returncode == 3
    assert _store(project) == before


# ---------------------------------------------------------------------------
# AC-5 / AC-5b / AC-6 — the listing tells deferred from open
# ---------------------------------------------------------------------------

def test_list_shows_deferred_in_its_own_section_with_the_reason(
    project: Path, item: str,
) -> None:
    open_id = append_triage_item(
        project, source="phaseQuality", severity="low", kind="bug",
        title="still open", detail="d",
    )
    defer(project, item_id=item, reason="waiting on upstream",
          revisit_at=FUTURE)
    out = _cli(project, "list").stdout
    assert "Deferred" in out
    assert "waiting on upstream" in out
    # Both are present, and the open one comes before the deferred section.
    assert open_id in out and item in out
    assert out.index(open_id) < out.index("Deferred") < out.index(item)


def test_list_says_nothing_about_deferral_when_there_is_none(
    project: Path, item: str,
) -> None:
    out = _cli(project, "list").stdout
    assert item in out
    assert "Deferred" not in out


def test_list_with_only_deferred_items_still_reports_no_open_work(
    project: Path, item: str,
) -> None:
    defer(project, item_id=item, reason="later", revisit_at=FUTURE)
    out = _cli(project, "list").stdout
    assert "No open triage items" in out
    assert "Deferred" in out and item in out


def test_list_renders_a_deferral_the_command_center_left_reasonless(
    project: Path, item: str,
) -> None:
    """Its route makes `reason` optional, so the CLI must not print `None`."""
    mark_status(project, item, new_status="snoozed", by="webui", reason=None)
    out = _cli(project, "list").stdout
    assert "Deferred" in out
    assert "None" not in out
    assert "no reason recorded" in out


def test_list_keeps_control_characters_out_of_the_deferred_section(
    project: Path,
) -> None:
    """AC-5b — the stored text comes from surfaces this CLI does not control."""
    hostile = append_triage_item(
        project, source="gh\x1b]2;evil\x07importer", severity="high",
        kind="bug", title="ti\x1btle", detail="d",
    )
    mark_status(project, hostile, new_status="snoozed", by="webui",
                reason="par\x1bked")
    out = _cli(project, "list").stdout
    assert "\x1b" not in out and "\x07" not in out
    assert "evil" in out  # the visible text survives; only the escape is gone


@pytest.mark.parametrize("verb", ["open", "deferred"])
def test_a_stored_newline_cannot_forge_a_listing_row(
    project: Path, verb: str,
) -> None:
    """The listing is line-oriented, so a newline is spoofing, not just noise.

    `strip_control_chars` keeps \\n and \\t for launch payloads; the scalar
    fields must not (external code review, OpenAI MED).
    """
    forged = append_triage_item(
        project, source="phaseQuality", severity="low", kind="bug",
        title="real\n- trg-fake000  severity=critical kind=bug source=x",
        detail="d",
    )
    if verb == "deferred":
        mark_status(project, forged, new_status="snoozed", by="webui",
                    reason="parked\n- trg-fake111  severity=critical")
    out = _cli(project, "list").stdout
    assert "trg-fake000" in out  # the text is shown …
    assert not any(                # … but never at the start of its own row
        line.lstrip().startswith("- trg-fake") for line in out.splitlines()
    )
    assert "\t" not in out


def test_list_json_now_carries_the_deferred_entry_in_its_own_section(
    project: Path, item: str,
) -> None:
    """The machine contract SEPARATES the two, it no longer omits one.

    This test asserted the opposite until iterate-2026-08-01-triage-defer-
    lifecycle: `list --json` returned open entries only, so the Command Center
    — which mirrors this contract in its own reader — showed a parked entry as
    gone, while the glossary promised it was still there. Version 2 is a
    deliberate break; WebUI-store consumer work is `trg-f2214310`.

    Still true, and still worth stating: no CI job in either repository re-runs
    this command against the Command Center's committed fixture, so drift here
    is caught by neither side automatically.
    """
    open_id = append_triage_item(
        project, source="phaseQuality", severity="low", kind="bug",
        title="still open", detail="d",
    )
    defer(project, item_id=item, reason="later", revisit_at=FUTURE)
    result = _cli(project, "list", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["contractVersion"] == 2
    assert [entry["id"] for entry in payload["open"]] == [open_id]
    assert payload["open"][0]["pendingDelivery"] is False
    [parked] = payload["deferred"]
    assert (parked["id"], parked["revisitAt"], parked["revisitDue"]) == (
        item, FUTURE, False,
    )
