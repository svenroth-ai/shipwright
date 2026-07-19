"""Record-boundary recovery at the COMPLIANCE event-log read sites (Tier B).

The plugin-side half of iterate-2026-07-19-…-readers. Three readers here used the
pre-fix idiom — bare ``json.loads(line)`` under an ``except json.JSONDecodeError``
that skips the WHOLE physical line — so a union-merge-concatenated line discarded
BOTH records. These feed the compliance change-history and the Group B/D audits,
where a dropped ``work_completed`` makes a step that happened read as one that
never did.

THE ADR-045 ANGLE
-----------------
The obvious one-line delegation used at the shared sites is unavailable here: the
plugin ships its own ``scripts/lib``, so a bare ``from lib import jsonl_records``
resolves to THAT package and raises ImportError (the ``sys.modules['lib']``
collision ADR-045 describes — verified empirically for this plugin, not assumed).

The remedy is NOT to duplicate the parser. The plugin already owns two tested,
pollution-free loaders that cross the boundary properly, and ``group_d`` already
imported one. These cases pin that the shared SSoT is what actually gets loaded —
a duplicate would satisfy the recovery assertions while silently drifting from
the contract it is supposed to mirror, so ``test_*_resolves_the_shared_module``
is the load-bearing case in this file.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.audit import _events_read, group_b, group_d  # noqa: E402
from scripts.lib.collectors import change_history  # noqa: E402

_SHARED_LIB = _HERE.parents[2] / "shared" / "scripts" / "lib"

_A = {
    "v": 1, "id": "evt-aaa", "ts": "2026-07-19T10:00:00+00:00",
    "type": "work_completed", "adr_id": "iterate-side-a", "run_id": "iterate-side-a",
}
_B = {
    "v": 1, "id": "evt-bbb", "ts": "2026-07-19T11:00:00+00:00",
    "type": "work_completed", "adr_id": "iterate-side-b", "run_id": "iterate-side-b",
}


def _concatenated(tmp_path: Path) -> Path:
    """One physical line holding TWO valid records — what union merge produces."""
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps(_A) + json.dumps(_B) + "\n", encoding="utf-8"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# AC4 — change_history: recover, keep warning, and stop leaking the handle
# ---------------------------------------------------------------------------

def test_change_history_recovers_both_records(tmp_path: Path) -> None:
    events = change_history._read_event_log(_concatenated(tmp_path))
    assert [e["id"] for e in events] == ["evt-aaa", "evt-bbb"]


def test_change_history_still_warns_on_an_unrecoverable_fragment(tmp_path: Path) -> None:
    """This site warns today; the governing invariant keeps it warning."""
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps(_A) + "{truncated\n", encoding="utf-8"
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        events = change_history._read_event_log(tmp_path)
    assert [e["id"] for e in events] == ["evt-aaa"]
    assert len(caught) == 1, "an unrecoverable fragment must not pass unreported"


def test_change_history_warning_does_not_echo_raw_event_data(tmp_path: Path) -> None:
    """Corruption diagnostics land in CI logs and audit output. Report WHERE and
    HOW MUCH, never the fragment text itself."""
    sentinel = "payload-that-must-not-be-echoed"
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps(_A) + "{" + sentinel + "\n", encoding="utf-8"
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        change_history._read_event_log(tmp_path)
    assert caught, "expected a warning to inspect"
    assert sentinel not in str(caught[0].message)


def test_change_history_releases_the_file_handle(tmp_path: Path) -> None:
    """The pre-fix reader iterated ``path.open(...)`` with no context manager and
    leaked the handle on every read — surfaced as a ResourceWarning while
    reproducing the record loss. Same defect PR #405 fixed in the shared reader."""
    _concatenated(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        change_history._read_event_log(tmp_path)
    leaked = [w for w in caught if issubclass(w.category, ResourceWarning)]
    assert leaked == [], f"leaked a file handle: {[str(w.message) for w in leaked]}"


# ---------------------------------------------------------------------------
# AC5 — group_b / group_d: recover, preserve None-on-absent, stay SILENT
# ---------------------------------------------------------------------------

def test_group_b_recovers_both_records(tmp_path: Path) -> None:
    assert [e["id"] for e in group_b._load_events(_concatenated(tmp_path))] == [
        "evt-aaa", "evt-bbb",
    ]


def test_group_d_recovers_both_records(tmp_path: Path) -> None:
    assert [e["id"] for e in group_d._load_events(_concatenated(tmp_path))] == [
        "evt-aaa", "evt-bbb",
    ]


def test_group_loaders_return_none_when_the_log_is_absent(tmp_path: Path) -> None:
    """None-on-absent is load-bearing: the groups distinguish 'no log' from
    'empty log' and must keep doing so after the delegation."""
    assert group_b._load_events(tmp_path) is None
    assert group_d._load_events(tmp_path) is None


def test_group_loaders_return_empty_list_for_an_existing_empty_log(tmp_path: Path) -> None:
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    assert group_b._load_events(tmp_path) == []
    assert group_d._load_events(tmp_path) == []


def test_group_loaders_stay_silent_on_corruption(tmp_path: Path) -> None:
    """Governing invariant: behaviour-preserving EXCEPT for record recovery.

    Both sites are silent today. Both external reviewers flagged that adding
    warnings here is unnecessary for the fix and risks contaminating audit
    output / tripping fail-on-stderr CI. Surfacing corruption belongs in the
    groups' own findings layer — filed as follow-up, deliberately not folded in.
    """
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps(_A) + "{truncated\n", encoding="utf-8"
    )
    for loader in (group_b._load_events, group_d._load_events):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert [e["id"] for e in loader(tmp_path)] == ["evt-aaa"]
        assert caught == [], f"{loader} must stay silent, emitted {[str(w.message) for w in caught]}"


def test_group_loaders_return_none_on_an_unreadable_log(tmp_path: Path, monkeypatch) -> None:
    """AC11 — ``None`` on OSError, not only on absence. Both groups relied on
    this branch before the delegation; an unreadable log must stay
    'undeterminable' rather than collapsing into an empty list."""
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps(_A) + "\n", encoding="utf-8"
    )
    shared = _events_read._jsonl_records()

    def _boom(_path):
        raise OSError("permission denied")

    monkeypatch.setattr(shared, "read_jsonl_records", _boom)
    assert group_b._load_events(tmp_path) is None
    assert group_d._load_events(tmp_path) is None


def test_change_history_warns_for_a_bare_scalar_line(tmp_path: Path) -> None:
    """AC12 — a scalar line was previously ACCEPTED here (``json.loads('5')``
    succeeded, so it entered the list as a non-dict). It is now a fragment, which
    at this already-warning site means it starts producing a warning.

    Observable change, so it is pinned rather than assumed: the value of the
    warning is that a non-record on the audit trail stops passing as an event.
    """
    (tmp_path / "shipwright_events.jsonl").write_text(
        "5\n" + json.dumps(_A) + "\n", encoding="utf-8"
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        events = change_history._read_event_log(tmp_path)
    assert [e["id"] for e in events] == ["evt-aaa"]
    assert len(caught) == 1
    assert all(isinstance(e, dict) for e in events)


def test_group_loaders_skip_a_bare_scalar_line(tmp_path: Path) -> None:
    """Both groups appended ``json.loads(line)`` with NO isinstance check, so a
    bare JSON scalar entered the list as a non-dict and crashed the first
    downstream ``.get()``. Only objects are records."""
    (tmp_path / "shipwright_events.jsonl").write_text(
        "5\n" + json.dumps(_A) + "\n", encoding="utf-8"
    )
    for loader in (group_b._load_events, group_d._load_events):
        events = loader(tmp_path)
        assert all(isinstance(e, dict) for e in events)
        assert [e["id"] for e in events] == ["evt-aaa"]


# ---------------------------------------------------------------------------
# AC9 — the shared SSoT is what actually crosses the ADR-045 boundary
# ---------------------------------------------------------------------------

def test_audit_loader_resolves_the_shared_module_not_a_plugin_local_copy() -> None:
    """The whole point of Tier B. If this ever resolves inside the plugin, a
    duplicate has crept in and will drift from the contract it mirrors."""
    module = _events_read._jsonl_records()
    assert Path(module.__file__).parent == _SHARED_LIB


def test_collector_loader_resolves_the_shared_module_not_a_plugin_local_copy() -> None:
    from scripts.lib.collectors._lib_loader import load_shared_lib
    assert Path(load_shared_lib("jsonl_records").__file__).parent == _SHARED_LIB


def test_group_modules_import_through_their_real_entry_point_path() -> None:
    """Import-mode smoke test. The audit groups are entered via
    ``scripts.audit`` (``_registry.py`` does ``from scripts.audit import
    group_b``), so the new sibling module must resolve under that exact
    convention — not merely under the test's own bootstrap."""
    from scripts.audit._registry import __name__ as registry_name  # noqa: F401
    from scripts.audit import _events_read as via_package
    assert via_package.load_events is _events_read.load_events
    assert group_b._load_events is _events_read.load_events
    assert group_d._load_events is _events_read.load_events
