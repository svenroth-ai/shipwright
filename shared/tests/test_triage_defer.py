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
from tools.triage_promote import defer, dismiss  # noqa: E402

TRIAGE_CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"


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
    result = defer(project, item_id=item, reason="waiting on upstream fix")
    assert result == {
        "id": item, "previousStatus": "triage",
        "newStatus": "snoozed", "reason": "waiting on upstream fix",
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
        defer(project, item_id=item, reason=reason)
    assert _store(project) == before


def test_defer_refuses_control_characters_in_the_reason(
    project: Path, item: str,
) -> None:
    with pytest.raises(ValueError, match="control character"):
        defer(project, item_id=item, reason="park\x1b]2;evil\x07it")


@pytest.mark.parametrize("already", ["dismissed", "snoozed", "promoted"])
def test_defer_refuses_an_already_decided_item(
    project: Path, item: str, already: str,
) -> None:
    """Asserted on the stored BYTES, not the resolved status.

    For ``already == "snoozed"`` a status assertion cannot fail: dropping the
    guard would append a second `snoozed` event and the resolved status would
    still read `snoozed`, so the test would stay green with the guard gone.
    """
    mark_status(project, item, new_status=already, by="x", reason="r")
    before = _store(project)
    with pytest.raises(ValueError, match="only `triage` is"):
        defer(project, item_id=item, reason="later")
    assert _store(project) == before


def test_defer_unknown_id_raises_key_error(project: Path, item: str) -> None:
    with pytest.raises(KeyError):
        defer(project, item_id="trg-deadbeef", reason="later")


def test_defer_without_a_store_raises_file_not_found(project: Path) -> None:
    with pytest.raises(FileNotFoundError):
        defer(project, item_id="trg-deadbeef", reason="later")


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
    result = _cli(project, "defer", item, "--reason", "revisit after v0.5")
    assert result.returncode == 0, result.stderr
    stored = _only(project)
    assert stored["status"] == "snoozed"
    assert stored["statusReason"] == "revisit after v0.5"
    assert stored["statusBy"] == "cli"
    assert "deferred" in result.stderr


@pytest.mark.parametrize("extra", [[], ["--reason", "  "]])
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
    result = _cli(project, verb, "trg-deadbeef", "--reason", "later")
    assert result.returncode == 2
    assert "not found" in result.stderr.lower()
    assert _store(project) == before


def test_cli_defer_refuses_an_already_decided_item(
    project: Path, item: str,
) -> None:
    mark_status(project, item, new_status="dismissed", by="x", reason="r")
    before = _store(project)
    result = _cli(project, "defer", item, "--reason", "later")
    assert result.returncode == 2
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
    defer(project, item_id=item, reason="waiting on upstream")
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
    defer(project, item_id=item, reason="later")
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


def test_list_json_stays_open_only_when_an_item_is_deferred(
    project: Path, item: str,
) -> None:
    """AC-6 — the machine contract stays open-only.

    Pins only that the array stays open-only. The Command Center deep-equals a
    committed snapshot that a human regenerates, and no CI job in either
    repository re-runs this command — so ANY other drift here, including a
    renamed field, is caught by neither side. The earlier "byte-for-byte"
    wording overstated that badly.
    """
    open_id = append_triage_item(
        project, source="phaseQuality", severity="low", kind="bug",
        title="still open", detail="d",
    )
    defer(project, item_id=item, reason="later")
    result = _cli(project, "list", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [entry["id"] for entry in payload] == [open_id]
    assert payload[0]["pendingDelivery"] is False
