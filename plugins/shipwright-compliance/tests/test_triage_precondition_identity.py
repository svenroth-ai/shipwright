"""The exception this plugin catches IS the one the store raises.

External plan review finding #3 for iterate-2026-07-31-it1-s2-expected-status:
this plugin reaches `shared/scripts/triage.py` by appending to `sys.path` at
call time, and three producers alias the function as `mark_status_fn`. If a
second import ever bound a different `triage` module object, `except
precondition_error` would compare against a DIFFERENT class object, silently
miss every refusal, and file it as a processing error instead — the failure
would look like a flaky compliance run, not like a lost operator decision.

Carrying the class out of the same `from triage import (...)` statement as
`mark_status` makes that impossible by construction. These tests run in THIS
plugin's own pytest session, which is the only place the divergence could
appear, and they fail the moment someone "tidies" the loader into a separate
top-level import.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from scripts.audit import triage_bundle as audit_bundle
from scripts.lib import sbom_generator, test_evidence
from scripts.lib.test_evidence import emit_test_failure_triage


def _barrier(triage_module, monkeypatch, project_root: Path, item_id: str) -> list:
    """Make the operator decide between the producer's read and its write.

    Returns the "fired" list so a test can assert the producer actually
    attempted a write — without that assertion a barrier that never runs would
    make the test vacuously green.
    """
    real = triage_module.mark_status
    fired: list = []

    def wrapper(*args, **kwargs):
        if not fired:
            fired.append(True)
            real(project_root, item_id, new_status="dismissed",
                 by="operator", reason="a person decided this")
        return real(*args, **kwargs)

    monkeypatch.setattr(triage_module, "mark_status", wrapper)
    return fired


@pytest.fixture
def triage_module():
    import triage  # type: ignore
    return triage


def test_audit_bundle_loader_yields_the_stores_own_exception(triage_module) -> None:
    """`_triage_api()`'s last element must be the very class `mark_status` raises."""
    *_, precondition_error = audit_bundle._triage_api()
    assert precondition_error is triage_module.StatusPreconditionError


@pytest.mark.parametrize(
    "module", [sbom_generator, test_evidence],
    ids=["sbom_generator", "test_evidence"],
)
def test_lib_loaders_yield_the_stores_own_exception(module, triage_module) -> None:
    """Same guarantee for the two `scripts/lib` producers."""
    *_, precondition_error = module._import_triage_api()
    assert precondition_error is triage_module.StatusPreconditionError


def test_the_loaders_also_yield_the_stores_own_mark_status(triage_module) -> None:
    """The pairing is the point: catching class X while calling a `mark_status`
    from module Y is precisely the bug this pins. Assert they travel together."""
    _, audit_mark, *_ = audit_bundle._triage_api()
    assert audit_mark is triage_module.mark_status
    for module in (sbom_generator, test_evidence):
        _, mark, *_ = module._import_triage_api()
        assert mark is triage_module.mark_status


def test_a_refusal_runs_the_producers_own_arm_and_is_not_an_error(
    tmp_path: Path, triage_module, monkeypatch, capsys,
) -> None:
    """Executes `sbom_generator`'s real `except precondition_error as exc` arm.

    This is the test whose absence let that arm ship reporting less than the
    others (Stage-1 review, finding 2): the identity assertions above prove the
    class matches, but only running the producer proves the arm is REACHED —
    that the refusal does not fall through to the generic handler, which would
    file it under `errors` and make a healthy interleaving look like a broken
    compliance run.

    The operator decides at a barrier, after the producer has taken its
    unlocked snapshot and before it writes. Deciding up front would filter the
    item out of the producer's own `status == "triage"` scan, so the arm would
    never run and this test would pass with the fix reverted.
    """
    item_id = triage_module.append_triage_item(
        tmp_path, source="sbom", severity="low", kind="compliance",
        title="t", detail="d", dedup_key="sbom:undeclared:gone/package.json",
    )

    real_mark_status = triage_module.mark_status
    fired = []

    def barrier(*args, **kwargs):
        if not fired:
            fired.append(True)
            real_mark_status(tmp_path, item_id, new_status="dismissed",
                             by="operator", reason="accepted licence")
        return real_mark_status(*args, **kwargs)

    monkeypatch.setattr(triage_module, "mark_status", barrier)

    # No workspaces here, so the producer's current key set is empty and its
    # resolve pass wants to close the item it just read as open.
    result = sbom_generator.emit_undeclared_triage(tmp_path)

    assert fired, "the producer never attempted a write - barrier never fired"
    assert result["dismissed"] == 0
    assert "error" not in result, (
        "a precondition refusal reached the generic handler - the dedicated "
        "arm did not catch it (class identity or arm ordering is wrong)"
    )
    assert "kept" in capsys.readouterr().err

    item = next(i for i in triage_module.read_all_items(tmp_path)
                if i["id"] == item_id)
    assert (item["statusBy"], item["statusReason"]) == (
        "operator", "accepted licence",
    )


def test_compliance_backlog_arm_runs_and_is_not_an_error(
    tmp_path: Path, triage_module, monkeypatch, capsys,
) -> None:
    """Executes `audit/triage_bundle._dismiss`'s own `except ... as exc` arm.

    An empty findings list means "nothing failing", so the producer wants to
    close every open backlog item — the `complianceResolved` path.
    """
    item_id = triage_module.append_triage_item(
        tmp_path, source="compliance", severity="high", kind="compliance",
        title="t", detail="d", dedup_key=audit_bundle.BACKLOG_PREFIX + "abc123",
    )
    fired = _barrier(triage_module, monkeypatch, tmp_path, item_id)

    report = SimpleNamespace(findings=[])
    result = audit_bundle.emit_compliance_backlog(
        tmp_path, report, run_id=None, commit=None,
    )

    assert fired, "the producer never attempted a write - barrier never fired"
    assert result["dismissed"] == 0
    assert "kept" in capsys.readouterr().err
    item = next(i for i in triage_module.read_all_items(tmp_path)
                if i["id"] == item_id)
    assert (item["statusBy"], item["statusReason"]) == (
        "operator", "a person decided this",
    )


def test_test_evidence_arm_runs_and_is_not_an_error(
    tmp_path: Path, triage_module, monkeypatch, capsys,
) -> None:
    """Executes `test_evidence`'s own `except ... as exc` arm.

    A failing unit layer creates the card; a later green run of the SAME layer
    is what makes the producer want to close it.
    """
    log = tmp_path / "shipwright_events.jsonl"

    def seed(event_id: str, ts: str, passed: int) -> None:
        with log.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps({
                "v": 1, "id": event_id, "ts": ts, "type": "test_run",
                "trigger": "iterate",
                "layers": {"unit": {"passed": passed, "total": 2}},
            }) + "\n")

    seed("evt-red01", "2026-05-21T11:00:00Z", 1)
    emit_test_failure_triage(tmp_path)
    [item] = [i for i in triage_module.read_all_items(tmp_path)
              if i.get("source") == "test-failure" or i.get("status") == "triage"]

    seed("evt-green1", "2026-05-21T15:00:00Z", 2)
    fired = _barrier(triage_module, monkeypatch, tmp_path, item["id"])
    result = emit_test_failure_triage(tmp_path)

    assert fired, "the producer never attempted a write - barrier never fired"
    assert result["dismissed"] == 0
    assert "error" not in result, (
        "a precondition refusal reached the generic handler instead of the "
        "dedicated arm"
    )
    assert "kept" in capsys.readouterr().err
    after = next(i for i in triage_module.read_all_items(tmp_path)
                 if i["id"] == item["id"])
    assert (after["statusBy"], after["statusReason"]) == (
        "operator", "a person decided this",
    )
