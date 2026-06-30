"""Usability iterate 2026-06-30 — navigable compliance artifacts.

New behaviors for test-evidence.md + traceability-matrix.md:
* AC-1 Test Progression Source → Verification Timeline row (cross-file).
* AC-2 Requirements Coverage `(iter)` → timeline row (same file).
* AC-3 per-FR in-document anchors.
* AC-4 Verification Timeline descending (newest first).
* AC-5 Verification Timeline FRs → coverage-row anchor.
* AC-6 commit → GitHub diff.
* AC-7 Event column prefers an authored `summary`.
* AC-9 honest unit-only note on the synthesized Full Suite Runs table.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.lib import event_display
from scripts.lib._rtm_links import (
    commit_cell,
    fr_anchor_id,
    resolve_repo_url,
    utc_date,
)
from scripts.lib.data_collector import (
    ComplianceData,
    RequirementInfo,
    TestRunEvent as _TestRunEvent,
    WorkEvent,
)
from scripts.lib.rtm_generator import generate as rtm_generate
from scripts.lib.test_evidence import generate as te_generate


def _req(fr="FR-01.01", text="Login works", split="01-auth"):
    return RequirementInfo(id=fr, text=text, priority="Must", split=split)


def _ev(eid, ts, *, source="iterate", frs=("FR-01.01",), passed=5, total=5,
        desc="work", summary="", commit="", section=""):
    return WorkEvent(
        id=eid, timestamp=ts, source=source, description=desc, summary=summary,
        commit=commit, section=section, tests_passed=passed, tests_total=total,
        affected_frs=list(frs),
    )


def _data(tmp_path, events, reqs=None):
    d = ComplianceData(project_root=tmp_path, timestamp="2026-06-30T00:00:00Z")
    d.requirements = reqs or [_req()]
    d.work_events = events
    return d


def _timeline(out: str) -> str:
    return out.split("## Verification Timeline")[1]


def _cov_row(out: str, fr="FR-01.01") -> str:
    return next(l for l in out.splitlines() if l.startswith(f"| [{fr}]"))


def _git_init_with_remote(root: Path, url: str) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=root,
                   check=True, capture_output=True)


# --- AC-7 event display name + summary round-trip ------------------------

class TestEventDisplayName:
    def test_prefers_summary(self):
        we = _ev("evt-12345678", "2026-06-01T00:00:00Z",
                 desc="raw technical text", summary="Plain human summary")
        assert event_display.event_display_name(we) == "Plain human summary"

    def test_falls_back_to_cleaned_description(self):
        we = _ev("evt-12345678", "2026-06-01T00:00:00Z", desc="iterate: fix the thing")
        assert event_display.event_display_name(we) == "fix the thing"

    def test_strips_iterate_fix_prefix(self):
        we = _ev("evt-12345678", "2026-06-01T00:00:00Z", desc="iterate fix: parse env")
        assert event_display.event_display_name(we) == "parse env"

    def test_falls_back_to_id_when_empty(self):
        we = _ev("evt-12345678", "2026-06-01T00:00:00Z", desc="")
        assert event_display.event_display_name(we) == "evt-12345678"

    def test_summary_round_trips_through_from_dict(self):
        we = WorkEvent.from_dict({
            "id": "evt-aaaa1111", "ts": "2026-06-01T00:00:00Z", "source": "iterate",
            "summary": "Readable one-liner", "description": "technical",
            "tests": {"passed": 1, "total": 1},
        })
        assert we.summary == "Readable one-liner"
        assert event_display.event_display_name(we) == "Readable one-liner"


# --- AC-1 Test Progression Source link -----------------------------------

class TestProgressionSourceLink:
    def test_canonical_iterate_links_cross_file(self, tmp_path):
        out = te_generate(_data(tmp_path, [_ev("evt-7620210f", "2026-06-01T00:00:00Z")]))
        assert "[iterate](traceability-matrix.md#evt-7620210f)" in out

    def test_noncanonical_id_stays_plain(self, tmp_path):
        out = te_generate(_data(tmp_path, [_ev("ev-x", "2026-06-01T00:00:00Z")]))
        assert "traceability-matrix.md#" not in out


# --- AC-2 Requirements Coverage (iter) link + AC-3 anchor ----------------

class TestCoverageLinks:
    def test_iter_token_links_same_file(self, tmp_path):
        out = rtm_generate(_data(tmp_path, [_ev("evt-7620210f", "2026-06-01T00:00:00Z")]))
        assert "([iter](#evt-7620210f))" in _cov_row(out)

    def test_build_source_stays_plain(self, tmp_path):
        out = rtm_generate(_data(tmp_path, [
            _ev("evt-7620210f", "2026-06-01T00:00:00Z", source="build", section="01-auth"),
        ]))
        row = _cov_row(out)
        assert "(build)" in row
        assert "[iter]" not in row

    def test_row_carries_in_document_anchor_after_link(self, tmp_path):
        out = rtm_generate(_data(tmp_path, [_ev("evt-7620210f", "2026-06-01T00:00:00Z")]))
        row = _cov_row(out)
        assert '<a id="rtm-fr-0101"></a>' in row
        # anchor sits AFTER the requirement link so the row prefix stays `| [FR-…]`
        assert row.index("](") < row.index('<a id="rtm-fr-0101"')


# --- AC-4 Verification Timeline descending -------------------------------

class TestTimelineDescending:
    def test_newest_first(self, tmp_path):
        out = rtm_generate(_data(tmp_path, [
            _ev("evt-00000001", "2026-06-01T00:00:00Z", desc="older"),
            _ev("evt-00000002", "2026-06-10T00:00:00Z", desc="newer"),
        ]))
        body = _timeline(out)
        assert body.index("newer") < body.index("older")

    def test_malformed_ts_sorts_last(self, tmp_path):
        out = rtm_generate(_data(tmp_path, [
            _ev("evt-00000003", "2026-06-05T00:00:00Z", desc="valid"),
            _ev("evt-00000004", "not-a-date", desc="broken"),
        ]))
        body = _timeline(out)
        assert body.index("valid") < body.index("broken")


# --- AC-5 Verification Timeline FR links ---------------------------------

class TestTimelineFrLinks:
    def test_declared_fr_links_to_anchor(self, tmp_path):
        out = rtm_generate(_data(tmp_path, [_ev("evt-00000001", "2026-06-01T00:00:00Z")]))
        assert "[FR-01.01](#rtm-fr-0101)" in _timeline(out)

    def test_unknown_fr_stays_plain(self, tmp_path):
        out = rtm_generate(_data(tmp_path, [
            _ev("evt-00000001", "2026-06-01T00:00:00Z", frs=("FR-09.99",)),
        ]))
        body = _timeline(out)
        assert "FR-09.99" in body
        assert "[FR-09.99](#rtm-" not in body


# --- AC-6 commit link ----------------------------------------------------

class TestCommitLink:
    def test_commit_cell_links_when_repo_url(self):
        assert commit_cell("abc1234def", "https://github.com/o/r") == \
            "[abc1234](https://github.com/o/r/commit/abc1234def)"

    def test_commit_cell_plain_without_url(self):
        assert commit_cell("abc1234def", "") == "abc1234"

    def test_commit_cell_dash_without_commit(self):
        assert commit_cell("", "https://github.com/o/r") == "—"

    def test_resolve_repo_url_https_strips_dotgit(self, tmp_path):
        _git_init_with_remote(tmp_path, "https://github.com/o/r.git")
        assert resolve_repo_url(tmp_path) == "https://github.com/o/r"

    def test_resolve_repo_url_ssh_normalized(self, tmp_path):
        _git_init_with_remote(tmp_path, "git@github.com:o/r.git")
        assert resolve_repo_url(tmp_path) == "https://github.com/o/r"

    def test_resolve_repo_url_empty_when_no_repo(self, tmp_path):
        assert resolve_repo_url(tmp_path) == ""

    def test_timeline_commit_links_when_resolvable(self, tmp_path):
        _git_init_with_remote(tmp_path, "https://github.com/o/r.git")
        out = rtm_generate(_data(tmp_path, [
            _ev("evt-00000001", "2026-06-01T00:00:00Z", commit="deadbeefcafe"),
        ]))
        assert "(https://github.com/o/r/commit/deadbeefcafe)" in _timeline(out)


# --- AC-9 synthesized Full Suite Runs honest note ------------------------

class TestFullSuiteNote:
    def test_synthesis_carries_note(self, tmp_path):
        out = te_generate(_data(tmp_path, [
            _ev("evt-00000001", "2026-06-01T00:00:00Z", passed=10, total=10),
        ]))
        assert "## Full Suite Runs" in out
        assert "no `test_run` events" in out

    def test_real_test_run_path_has_no_note(self, tmp_path):
        data = _data(tmp_path, [_ev("evt-00000001", "2026-06-01T00:00:00Z", passed=1, total=1)])
        data.test_runs = [_TestRunEvent(
            id="tr-1", timestamp="2026-06-01T00:00:00Z", trigger="ci",
            unit_passed=5, unit_total=5, unit_evaluated=True,
        )]
        out = te_generate(data)
        assert "## Full Suite Runs" in out
        assert "no `test_run` events" not in out


# --- meta: EVENT_ID_RE drift pin -----------------------------------------

def test_event_id_re_matches_rtm_render_pattern():
    from scripts.lib._rtm_reconciliation_render import _EVENT_ID_RE
    assert event_display.EVENT_ID_RE.pattern == _EVENT_ID_RE.pattern


def test_fr_anchor_id_shape():
    assert fr_anchor_id("FR-01.01") == "rtm-fr-0101"


def test_f5b_reference_documents_summary_field():
    """AC-8: the iterate F5b reference instructs authoring a plain `summary`."""
    f5b = (Path(__file__).resolve().parents[2]
           / "shipwright-iterate" / "skills" / "iterate" / "references" / "F5b.md")
    text = f5b.read_text(encoding="utf-8")
    assert '"summary"' in text
    assert "event-extras-json" in text


# --- Timeline Date column UTC-normalized (cross-timezone monotonicity) --------

class TestTimelineUtcDate:
    def test_utc_date_normalizes_offset(self):
        # 00:27 at +02:00 is 22:27 the PREVIOUS day in UTC.
        assert utc_date("2026-05-13T00:27:38+02:00") == "2026-05-12"
        assert utc_date("2026-05-12T22:51:57.835014+00:00") == "2026-05-12"
        assert utc_date("2026-05-12T10:00:00Z") == "2026-05-12"

    def test_utc_date_fallback_on_unparseable(self):
        assert utc_date("garbage") == "garbage"
        assert utc_date("") == ""

    def test_timeline_date_column_monotonic_across_timezones(self, tmp_path):
        # Real-data repro: a +02:00 near-midnight event sorts by UTC instant but
        # previously printed its local date (one day ahead) → visual inversion.
        out = rtm_generate(_data(tmp_path, [
            _ev("evt-0c3127ae", "2026-05-12T22:51:57+00:00", desc="utc event"),
            _ev("evt-a0277cdf", "2026-05-13T00:27:38+02:00", desc="plus2 event"),
        ]))
        tl = _timeline(out)
        # The +02:00 event renders its UTC date (05-12), not its local 05-13.
        plus2_row = next(l for l in tl.splitlines() if "plus2 event" in l)
        assert plus2_row.split("|")[-2].strip() == "2026-05-12"
        assert "2026-05-13" not in plus2_row
        # Date column is non-increasing (no inversion).
        rows = [l for l in tl.splitlines()
                if l.startswith("| ") and "|---" not in l and not l.startswith("| Event ")]
        dates = [r.split("|")[-2].strip() for r in rows]
        dates = [d for d in dates if len(d) == 10 and d[4] == "-"]
        assert all(dates[i] >= dates[i + 1] for i in range(len(dates) - 1))
