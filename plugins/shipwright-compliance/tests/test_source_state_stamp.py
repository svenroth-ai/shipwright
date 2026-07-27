"""Compliance evidence documents name the state they describe.

Call site 2 of the artifact-state stamp (card ``trg-4d5b6a56``, FR-01.10). Every
evidence document carried ``Generated: <timestamp>``, which says *when* it was
written but not *which state* it describes — and a timestamp cannot distinguish a
document regenerated from an old state from one regenerated from the current one.

Two guarantees are pinned here:

* all five documents carry exactly one ``Source-State:`` line, directly under
  ``Generated:``;
* the run id and the timestamp are read off **one** work event, so the two header
  lines can never describe two different events (external review, edge-case/high).

Plus the AC5 guarantee that this is *disclosure and not a new gate*: Group E's
snapshot compare normalises the banner away exactly like ``Generated:``, so an
on-demand regen cannot newly report a document as stale.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[4] / "shared" / "scripts")
)

from scripts.audit import audit_staleness  # noqa: E402
from scripts.lib.change_history import generate as generate_change_history  # noqa: E402
from scripts.lib.collectors.change_history import (  # noqa: E402
    latest_event_timestamp,
    latest_work_event,
    run_id_of,
)
from scripts.lib.compliance_report import generate as generate_dashboard  # noqa: E402
from scripts.lib.data_collector import ComplianceData, WorkEvent  # noqa: E402
from scripts.lib.rtm_generator import generate as generate_rtm  # noqa: E402
from scripts.lib.sbom_generator import generate as generate_sbom  # noqa: E402
from scripts.lib.test_evidence import generate as generate_test_evidence  # noqa: E402
from source_state import BANNER_PREFIX, UNKNOWN_RUN, parse_banner_line  # noqa: E402

RUN = "iterate-2026-07-27-artifact-state-stamping"
OLDER = "iterate-2026-07-20-earlier"

#: Every renderer that emits an evidence document, by the doc it produces.
RENDERERS = {
    "rtm": generate_rtm,
    "test_evidence": generate_test_evidence,
    "change_history": generate_change_history,
    "sbom": generate_sbom,
    "dashboard": generate_dashboard,
}


def _event(run_id: str, ts: str) -> WorkEvent:
    # run_id travels as adr_id — see finalize_iterate.py ("storing run_id as adr_id").
    return WorkEvent(id=f"evt-{run_id}", timestamp=ts, source="iterate", adr_id=run_id)


def _data(project_root: Path, events: list[WorkEvent] | None = None) -> ComplianceData:
    events = events if events is not None else [_event(RUN, "2026-07-27T10:00:00Z")]
    latest = latest_work_event(events)
    return ComplianceData(
        project_root=project_root,
        work_events=events,
        timestamp=latest_event_timestamp(events),
        run_id=run_id_of(latest),
    )


def _header(doc: str) -> list[str]:
    """The contiguous non-blank header block below the H1."""
    lines = doc.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("Generated:"))
    block = []
    for ln in lines[start:]:
        if not ln.strip():
            break
        block.append(ln)
    return block


# --------------------------------------------------------------------------
# AC3 — every document carries the line, in the right place, exactly once
# --------------------------------------------------------------------------


class TestAllFiveRenderers:
    @pytest.mark.parametrize("key", sorted(RENDERERS))
    def test_emits_the_banner_directly_under_generated(self, key, tmp_path: Path):
        doc = RENDERERS[key](_data(tmp_path))
        header = _header(doc)
        assert header[0].startswith("Generated:")
        assert header[1].startswith(BANNER_PREFIX), f"{key}: banner not under Generated:"

    @pytest.mark.parametrize("key", sorted(RENDERERS))
    def test_emits_the_banner_exactly_once(self, key, tmp_path: Path):
        doc = RENDERERS[key](_data(tmp_path))
        assert sum(ln.startswith(BANNER_PREFIX) for ln in doc.splitlines()) == 1

    @pytest.mark.parametrize("key", sorted(RENDERERS))
    def test_the_banner_names_the_run(self, key, tmp_path: Path):
        assert parse_banner_line(RENDERERS[key](_data(tmp_path))).run_id == RUN

    @pytest.mark.parametrize("key", sorted(RENDERERS))
    def test_rendering_twice_is_byte_stable(self, key, tmp_path: Path):
        # A banner that drifted per call would leave every tracked MD permanently
        # dirty — the exact defect deterministic timestamps were introduced to fix.
        assert RENDERERS[key](_data(tmp_path)) == RENDERERS[key](_data(tmp_path))

    @pytest.mark.parametrize("key", sorted(RENDERERS))
    def test_no_events_renders_unknown_not_a_guess(self, key, tmp_path: Path):
        doc = RENDERERS[key](_data(tmp_path, events=[]))
        assert f"run={UNKNOWN_RUN}" in doc
        assert "Generated: (no events)" in doc

    @pytest.mark.parametrize("key", sorted(RENDERERS))
    def test_an_event_without_a_run_id_renders_unknown(self, key, tmp_path: Path):
        events = [WorkEvent(id="e1", timestamp="2026-07-27T10:00:00Z", source="build")]
        assert f"run={UNKNOWN_RUN}" in RENDERERS[key](_data(tmp_path, events=events))


# --------------------------------------------------------------------------
# AC4 — one event, read once: the two header lines cannot disagree
# --------------------------------------------------------------------------


class TestOneEventForBothFields:
    def test_latest_work_event_and_timestamp_agree(self):
        events = [
            _event(OLDER, "2026-07-20T08:00:00Z"),
            _event(RUN, "2026-07-27T10:00:00Z"),
            _event("iterate-2026-07-25-middle", "2026-07-25T09:00:00Z"),
        ]
        latest = latest_work_event(events)
        assert latest.adr_id == RUN
        assert latest.timestamp == latest_event_timestamp(events)

    def test_event_order_in_the_log_does_not_change_the_answer(self):
        newest = _event(RUN, "2026-07-27T10:00:00Z")
        older = _event(OLDER, "2026-07-20T08:00:00Z")
        assert latest_work_event([newest, older]).adr_id == RUN
        assert latest_work_event([older, newest]).adr_id == RUN

    @pytest.mark.parametrize("key", sorted(RENDERERS))
    def test_document_reports_the_newest_run_not_an_earlier_one(self, key, tmp_path: Path):
        events = [_event(OLDER, "2026-07-20T08:00:00Z"), _event(RUN, "2026-07-27T10:00:00Z")]
        doc = RENDERERS[key](_data(tmp_path, events=events))
        assert parse_banner_line(doc).run_id == RUN
        assert OLDER not in _header(doc)[1]

    def test_no_events_yields_no_event(self):
        assert latest_work_event([]) is None

    def test_events_with_unusable_timestamps_yield_no_event(self):
        # Mirrors latest_event_timestamp's "(no events)" fallback rather than
        # picking an arbitrary event — the two must not diverge.
        events = [WorkEvent(id="e1", timestamp="", source="iterate", adr_id=RUN)]
        assert latest_work_event(events) is None
        assert latest_event_timestamp(events) == "(no events)"


# --------------------------------------------------------------------------
# AC5 — disclosure, not a new gate
# --------------------------------------------------------------------------


class TestGroupEStalenessUnaffected:
    def test_normalize_strips_the_banner(self):
        text = f"# RTM\nGenerated: x\n{BANNER_PREFIX} run={RUN}\nbody\n"
        assert audit_staleness.normalize(text) == "# RTM\nbody\n"

    def test_two_documents_differing_only_by_run_are_not_stale(self):
        # The case this protects: `update_compliance.py` writes a fresh,
        # uncommitted regen for on-demand inspection. Before the stamp, an
        # unchanged body compared equal. If the banner were NOT normalised, that
        # regen would start reporting every document as hand-edited.
        a = f"# RTM\nGenerated: t1\n{BANNER_PREFIX} run={RUN}\n\nsame body\n"
        b = f"# RTM\nGenerated: t2\n{BANNER_PREFIX} run={OLDER}\n\nsame body\n"
        assert audit_staleness.normalize(a) == audit_staleness.normalize(b)

    def test_a_real_body_change_is_still_detected(self):
        a = f"# RTM\nGenerated: t1\n{BANNER_PREFIX} run={RUN}\n\nbody one\n"
        b = f"# RTM\nGenerated: t1\n{BANNER_PREFIX} run={RUN}\n\nbody two\n"
        assert audit_staleness.normalize(a) != audit_staleness.normalize(b)

    def test_a_mid_line_mention_is_not_stripped(self):
        text = f"the {BANNER_PREFIX} line is written by the renderer\n"
        assert audit_staleness.normalize(text) == text

    def test_normalize_still_strips_generated(self):
        assert audit_staleness.normalize("Generated: x\nbody\n") == "body\n"


class TestAdrReferenceIsNotARun:
    """``adr_id`` is dual-purpose, so it cannot be read as a run id unconditionally.

    ``finalize_iterate`` stores the iterate run id in ``adr_id``, but
    ``record_event.py`` documents ``--adr-id`` as an ADR reference and build-phase
    events use it that way. Reported by external code review: without a guard a
    build-phase newest event renders ``Source-State: run=ADR-055``, naming a decision
    record as a run.
    """

    @pytest.mark.parametrize("adr", ["ADR-055", "adr-7", "ADR-0001"])
    def test_an_adr_reference_yields_no_run_id(self, adr):
        assert run_id_of(_event(adr, "2026-07-27T10:00:00Z")) is None

    @pytest.mark.parametrize("value", [RUN, "iterate-2026-07-27-adr-tooling"])
    def test_a_real_run_id_is_returned(self, value):
        assert run_id_of(_event(value, "2026-07-27T10:00:00Z")) == value

    def test_missing_and_blank_are_none(self):
        assert run_id_of(None) is None
        assert run_id_of(WorkEvent(id="e", timestamp="t", source="build")) is None
        assert run_id_of(_event("   ", "2026-07-27T10:00:00Z")) is None

    @pytest.mark.parametrize("key", sorted(RENDERERS))
    def test_a_document_never_labels_an_adr_as_a_run(self, key, tmp_path: Path):
        events = [_event("ADR-055", "2026-07-27T10:00:00Z")]
        doc = RENDERERS[key](_data(tmp_path, events=events))
        assert f"run={UNKNOWN_RUN}" in doc
        assert "run=ADR-055" not in doc


class TestAuditStalenessStaysFilePathLoadable:
    """``audit_staleness.py`` must import cleanly when loaded BY FILE PATH.

    Two existing tests in other pytest sessions load this module via
    ``spec_from_file_location`` — ``shipwright-security``'s
    ``test_finalize_security_compliance`` and ``shared``'s ``test_integrate_main``. In
    those sessions ``scripts`` resolves to a *different* plugin's namespace, so a
    module-level ``from scripts.lib… import`` raises ``ModuleNotFoundError``: green
    from this plugin, red in CI. That is the ADR-045 lib-collision landmine, and it
    was introduced here once (by a code-review fix) and caught by the doubt reviewer.

    Guarded locally so the constraint does not depend on tests in other plugins that
    someone could reasonably delete. The check is STATIC: exec'ing the module under a
    stubbed ``scripts`` namespace fails inside ``dataclasses`` for harness reasons
    (it resolves ``cls.__module__`` through ``sys.modules``), which would test the
    probe rather than the product. The live dynamic coverage is the two real
    file-path loads in the security and shared sessions.
    """

    MODULE = Path(__file__).resolve().parents[1] / "scripts" / "audit" / "audit_staleness.py"

    def test_no_module_level_cross_package_import(self):
        source = self.MODULE.read_text(encoding="utf-8")
        offenders = [
            ln.strip() for ln in source.splitlines()
            if ln.startswith(("from scripts.", "import scripts."))
        ]
        assert not offenders, (
            "audit_staleness is loaded by file path from other plugins' sessions, "
            f"where `scripts` is a different package. Reach shared code through the "
            f"absolute parents[4] path bootstrap instead. Offending: {offenders}"
        )
