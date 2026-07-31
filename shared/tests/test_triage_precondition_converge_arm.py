"""The accepted-risk converger keeps an item a person already decided.

The ninth automatic flip site. It gets its own file because its two neighbours
— `shared/tests/test_accepted_risks_converge_cli.py` (284) and
`test_triage_precondition_callers.py` (282) — are both close enough to the
300-line cap that adding here would have pushed one over and minted a bloat
baseline entry for a test file that does not need one.

This arm is the one that reports on **stdout** rather than stderr: this
command's whole report is stdout, including the `dismissed` line it prints
beside this one. That difference is deliberate and is what this file pins.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for _p in (str(_SHARED_SCRIPTS), str(_SHARED_SCRIPTS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import alert_convergence  # noqa: E402
import triage  # noqa: E402
from accepted_risks_converge import _apply_triage  # noqa: E402


def _plan_for(item: dict) -> SimpleNamespace:
    return SimpleNamespace(triage_dismiss=[(SimpleNamespace(id="AR-1"), item)])


def test_converger_keeps_a_decided_item_and_reports_no_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Executes `_apply_triage`'s `except StatusPreconditionError` arm.

    The plan was built from an unlocked read, so the item it names as open can
    have been decided since. The refusal must NOT count as a failure: this
    function's return value is a failure count that the CLI turns into a
    non-zero exit, so treating a healthy interleaving as a failure would make
    `converge --apply` exit 1 on a correct run.
    """
    item_id = triage.append_triage_item(
        tmp_path, source="security", severity="high", kind="bug",
        title="t", detail="d", dedup_key="semgrep:rule:a.py:1",
    )
    real_mark_status = triage.mark_status
    fired: list = []

    def barrier(*args, **kwargs):
        if not fired:
            fired.append(True)
            real_mark_status(tmp_path, item_id, new_status="dismissed",
                             by="operator", reason="a person decided this")
        return real_mark_status(*args, **kwargs)

    monkeypatch.setattr(triage, "mark_status", barrier)

    failures = _apply_triage(_plan_for({"id": item_id}), tmp_path)

    assert fired, "the converger never attempted a write - barrier never fired"
    assert failures == 0
    out = capsys.readouterr()
    assert "kept" in out.out, "the kept line belongs on stdout with the report"
    assert out.err == "", "nothing about this outcome belongs on stderr"

    item = next(i for i in triage.read_all_items(tmp_path) if i["id"] == item_id)
    assert (item["statusBy"], item["statusReason"]) == (
        "operator", "a person decided this",
    )


def test_converger_still_dismisses_an_untouched_item(tmp_path: Path) -> None:
    """The negative control: an arm that refused everything would pass the
    test above and silently stop the converger from doing its job."""
    item_id = triage.append_triage_item(
        tmp_path, source="security", severity="high", kind="bug",
        title="t", detail="d", dedup_key="semgrep:rule:b.py:2",
    )
    assert _apply_triage(_plan_for({"id": item_id}), tmp_path) == 0
    item = next(i for i in triage.read_all_items(tmp_path) if i["id"] == item_id)
    assert (item["status"], item["statusBy"], item["statusReason"]) == (
        "dismissed", alert_convergence.TRIAGE_DISMISSER,
        alert_convergence.TRIAGE_REASON,
    )


def test_a_real_failure_is_still_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The precondition arm must not have swallowed genuine errors on its way
    in — a store outage still has to reach the failure count."""
    def boom(*_a, **_k):
        raise RuntimeError("store outage")

    monkeypatch.setattr(triage, "mark_status", boom)
    assert _apply_triage(_plan_for({"id": "trg-whatever"}), tmp_path) == 1
