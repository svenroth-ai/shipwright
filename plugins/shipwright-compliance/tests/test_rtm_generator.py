"""Tests for rtm_generator.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.lib.data_collector import (
    ComplianceData, RequirementInfo, WorkEvent, collect_all,
)
from scripts.lib.rtm_generator import generate, generate_file


def _git(args: list[str], cwd: Path) -> None:
    """Run a git command in ``cwd``, raising on failure."""
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )


class TestGenerate:
    def test_produces_markdown(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "# Requirements Traceability Matrix" in result
        assert "## Section Traceability" in result
        assert "## Coverage Summary" in result

    def test_contains_section_data(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "01-login" in result
        assert "02-rbac" in result
        assert "03-profile" in result
        assert "abc123def456" in result  # commit hash

    def test_no_traceability_flow_diagram(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Traceability Flow" not in result
        assert "flowchart TD" not in result

    def test_summary_metrics(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "| Total splits | 3 |" in result
        assert "| Total sections | 3 |" in result
        assert "| Traceability coverage | 100% |" in result

    def test_empty_data(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        result = generate(data)
        assert "No sections available yet" in result

    def test_section_pass_status(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        # Section traceability shows PASS for sections with green unit tests
        assert "PASS" in result

    def test_findings_in_summary(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        # 03-profile has 2 findings (1 fixed, 1 deferred) -> totals in summary
        assert "| Total review findings | 3 |" in result
        assert "| Unresolved findings | 1 |" in result


def _make_data(tmp_path, *, baseline=0, tests_passed=830, tests_total=831):
    """Helper to build ComplianceData with one FR and one work event."""
    data = ComplianceData(project_root=tmp_path, timestamp="2026-04-06T00:00:00Z")
    data.baseline_failure_count = baseline
    we = WorkEvent(
        id="ev-1", timestamp="2026-04-06T10:00:00Z", source="iterate",
        description="Add feature", tests_passed=tests_passed, tests_total=tests_total,
        affected_frs=["FR-01.01"],
    )
    data.work_events = [we]
    data.requirements = [
        RequirementInfo(id="FR-01.01", text="Login works", priority="Must", split="01-auth"),
    ]
    return data


class TestKnownFailures:
    def test_baseline_failures_give_covered_baseline(self, tmp_path: Path):
        """FRs with failures <= baseline get COVERED (baseline) not FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "COVERED (baseline)" in result
        assert "| FAIL |" not in result

    def test_failures_beyond_baseline_still_fail(self, tmp_path: Path):
        """FRs with failures > baseline still get FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=828, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "COVERED (baseline)" not in result

    def test_no_known_failures_unchanged(self, tmp_path: Path):
        """Without known_failures, behavior is identical to current."""
        data = _make_data(tmp_path, baseline=0, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "COVERED (baseline)" not in result

    def test_all_passing_ignores_baseline(self, tmp_path: Path):
        """When all tests pass, status is COVERED regardless of baseline."""
        data = _make_data(tmp_path, baseline=1, tests_passed=831, tests_total=831)
        result = generate(data)
        assert "COVERED" in result
        assert "baseline" not in result


class TestRtmAdoptedProjectWorktree:
    """F0.5 end-to-end: RTM generation from a git worktree of an adopted project.

    Two things must hold for real, event-sourced coverage from a worktree:
      * Bug A — the adopted spec uses a 6-column FR table (parsed correctly).
      * Per-tree event log (iterate-2026-05-29-events-jsonl-worktree-commit) —
        shipwright_events.jsonl is a tracked, committed artifact, so a fresh
        worktree checkout CARRIES it and RTM reads the worktree's own copy.
    Without these the RTM falls back to the legacy section-count path and an
    adopted project (0 build sections) emits "| Traceability coverage | 0% |" —
    which the check_rtm_coverage pre-commit hook soft-blocks.
    """

    SIX_COL_SPEC = (
        "# Specification - adopted\n\n"
        "## Functional Requirements\n\n"
        "| ID | Name | Priority | Description | Source | Confidence |\n"
        "|----|------|----------|-------------|--------|------------|\n"
        "| FR-01.01 | dashboard | Must | User views active projects. | src/app/dashboard/page.tsx | 0.82 |\n"
        "| FR-01.02 | login | Must | User authenticates via magic link. | src/app/login/page.tsx | 0.91 |\n"
        "| FR-01.03 | settings | Should | User edits profile preferences. | src/app/settings/page.tsx | 0.55 |\n"
    )

    def _build_adopted_project(self, root: Path) -> None:
        """Create a completed adopted project: 1 planning split, 0 build sections."""
        root.mkdir(parents=True, exist_ok=True)
        _git(["init"], root)
        _git(["config", "user.email", "test@example.com"], root)
        _git(["config", "user.name", "Test"], root)

        (root / "shipwright_run_config.json").write_text(
            json.dumps({"status": "complete", "profile": "supabase-nextjs"}),
            encoding="utf-8",
        )
        (root / "shipwright_project_config.json").write_text(
            json.dumps({"splits": [{"name": "01-adopted", "status": "complete"}]}),
            encoding="utf-8",
        )
        planning = root / ".shipwright" / "planning" / "01-adopted"
        planning.mkdir(parents=True)
        (planning / "spec.md").write_text(self.SIX_COL_SPEC, encoding="utf-8")

        # The event log is a tracked, per-tree artifact — written BEFORE the
        # commit so it lands in the baseline and a fresh worktree CARRIES it.
        events = [{
            "id": "evt-adopt-1", "type": "work_completed", "source": "iterate",
            "ts": "2026-05-15T10:00:00Z", "commit": "deadbeef",
            "affected_frs": ["FR-01.01", "FR-01.02", "FR-01.03"],
            "tests": {"passed": 12, "total": 12},
        }]
        (root / "shipwright_events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )

        # Tracked artifacts (incl. the event log) go into the commit so the
        # worktree carries them.
        _git(["add", "-A"], root)
        _git(["commit", "-m", "adopt baseline"], root)

    def test_rtm_from_worktree_shows_real_coverage(self, tmp_path: Path):
        main = tmp_path / "adopted-main"
        self._build_adopted_project(main)

        worktree = tmp_path / "wt"
        _git(["worktree", "add", str(worktree)], main)
        # The worktree carries BOTH the committed spec and the committed log
        # (per-tree model — RTM reads the worktree's own copy).
        assert (worktree / ".shipwright" / "planning" / "01-adopted" / "spec.md").exists()
        assert (worktree / "shipwright_events.jsonl").exists()

        rtm_path = generate_file(worktree)
        rtm = rtm_path.read_text(encoding="utf-8")

        # Bug B regression guard: the legacy 0%-coverage path is NOT taken.
        assert "| Traceability coverage | 0% |" not in rtm
        # Bug A: all three 6-column FR rows surfaced.
        for fr in ("FR-01.01", "FR-01.02", "FR-01.03"):
            assert fr in rtm
        # Event-sourced coverage summary present with real counts.
        assert "| Requirements verified | 3/3 |" in rtm
        assert "COVERED" in rtm


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "traceability-matrix.md"
        content = path.read_text(encoding="utf-8")
        assert "# Requirements Traceability Matrix" in content

    def test_creates_compliance_dir(self, tmp_path: Path):
        """If compliance/ doesn't exist, generate_file creates it."""
        root = tmp_path / "project"
        root.mkdir()
        data = ComplianceData(project_root=root)
        data.timestamp = "2026-03-21T14:00:00Z"
        path = generate_file(root, data)
        assert (root / ".shipwright" / "compliance").exists()
        assert path.exists()


# ---------------------------------------------------------------------------
# Iterate B.4 (ADR-058) — RTM ↔ Triage deep-link + Coverage Summary rewrite
# ---------------------------------------------------------------------------

import sys as _sys


def _ensure_triage_on_path():
    shared = Path(__file__).resolve().parents[3] / "shared" / "scripts"
    if str(shared) not in _sys.path:
        _sys.path.insert(0, str(shared))


def _seed_open_triage_item(project_root: Path, *, fr_id: str, item_id: str | None = None):
    """Append one open `source="test-evidence"` triage item with frId set."""
    _ensure_triage_on_path()
    from triage import append_triage_item  # type: ignore
    return append_triage_item(
        project_root,
        source="test-evidence",
        severity="high",
        kind="bug",
        title=f"Test failures for {fr_id}",
        detail=f"{fr_id} regression",
        fr_id=fr_id,
    )


class TestRtmTriageDeepLink:
    """Iterate B.4 (ADR-058) — FAIL → trg-XXX deep-link rendering."""

    def test_fr_with_open_triage_renders_deep_link(self, tmp_path: Path):
        data = _make_data(tmp_path, baseline=0, tests_passed=831, tests_total=831)
        _seed_open_triage_item(tmp_path, fr_id="FR-01.01")
        result = generate(data)
        # Status cell carries FAIL → [trg-XXX](...#trg-XXX)
        assert "FAIL → [trg-" in result
        assert "../agent_docs/triage_inbox.md#trg-" in result
        # The previous COVERED state is overridden by the open triage.
        # (Look at the requirements table row specifically — coverage summary
        # below may still mention COVERED counts for sibling rows.)
        rows = [l for l in result.splitlines() if l.startswith("| [FR-01.01]")]
        assert rows, "FR-01.01 row missing"
        assert "COVERED" not in rows[0]

    def test_open_triage_overrides_baseline_status(self, tmp_path: Path):
        """Even COVERED (baseline) flips to FAIL when triage card is open."""
        data = _make_data(tmp_path, baseline=1, tests_passed=830, tests_total=831)
        _seed_open_triage_item(tmp_path, fr_id="FR-01.01")
        result = generate(data)
        rows = [l for l in result.splitlines() if l.startswith("| [FR-01.01]")]
        assert "FAIL → [trg-" in rows[0]
        assert "COVERED (baseline)" not in rows[0]

    def test_promoted_triage_does_not_show(self, tmp_path: Path):
        """Promoted / dismissed items don't render deep-links (terminal status)."""
        data = _make_data(tmp_path, baseline=0, tests_passed=831, tests_total=831)
        _ensure_triage_on_path()
        from triage import append_triage_item, mark_status  # type: ignore
        item_id = append_triage_item(
            tmp_path, source="test-evidence", severity="high",
            kind="bug", title="x", detail="y", fr_id="FR-01.01",
        )
        mark_status(tmp_path, item_id, new_status="promoted", by="user",
                    promoted_task_id="TASK-1")
        result = generate(data)
        rows = [l for l in result.splitlines() if l.startswith("| [FR-01.01]")]
        assert "FAIL → [trg-" not in rows[0]
        assert "COVERED" in rows[0]

    def test_item_without_fr_id_ignored(self, tmp_path: Path):
        """Triage items without frId don't appear on any FR row."""
        data = _make_data(tmp_path, baseline=0, tests_passed=831, tests_total=831)
        _ensure_triage_on_path()
        from triage import append_triage_item  # type: ignore
        append_triage_item(
            tmp_path, source="sbom", severity="low", kind="compliance",
            title="x", detail="y",  # no fr_id
        )
        result = generate(data)
        assert "FAIL → [trg-" not in result

    def test_multiple_items_per_fr_render_all(self, tmp_path: Path):
        data = _make_data(tmp_path, baseline=0, tests_passed=831, tests_total=831)
        # Two items — record their IDs to assert sort order (code-review-M4).
        id_a = _seed_open_triage_item(tmp_path, fr_id="FR-01.01")
        id_b = _seed_open_triage_item(tmp_path, fr_id="FR-01.01")
        result = generate(data)
        rows = [l for l in result.splitlines() if l.startswith("| [FR-01.01]")]
        assert rows[0].count("FAIL → [trg-") == 2
        # AC-3: sorted ascending by item id.
        sorted_ids = sorted([id_a, id_b])
        first_idx = rows[0].index(f"FAIL → [{sorted_ids[0]}]")
        second_idx = rows[0].index(f"FAIL → [{sorted_ids[1]}]")
        assert first_idx < second_idx, "FAIL deep-links must render in sorted order"


class TestRtmCoverageSummaryRewrite:
    """Iterate B.4 (ADR-058) — three operator-actionable subsections."""

    def _make_multi_fr_data(self, tmp_path: Path):
        data = ComplianceData(project_root=tmp_path, timestamp="2026-05-21T00:00:00Z")
        data.requirements = [
            RequirementInfo(id="FR-01.01", text="Login works", priority="Must", split="01-auth"),
            RequirementInfo(id="FR-01.02", text="Logout works", priority="Must", split="01-auth"),
            RequirementInfo(id="FR-02.01", text="Profile edit", priority="Should", split="02-profile"),
        ]
        # FR-01.01 verified recently
        data.work_events = [WorkEvent(
            id="ev-recent", timestamp="2026-05-20T10:00:00Z", source="iterate",
            description="login", tests_passed=5, tests_total=5,
            affected_frs=["FR-01.01"],
        )]
        return data

    def test_frs_without_tests_section(self, tmp_path: Path):
        data = self._make_multi_fr_data(tmp_path)
        result = generate(data)
        assert "### FRs without tests" in result
        # FR-01.02 + FR-02.01 are unverified → listed.
        assert "FR-01.02" in result
        assert "FR-02.01" in result
        # FR-01.01 was verified → NOT in the no-tests section.
        no_tests_block = result.split("### FRs without tests")[1].split("###")[0]
        assert "FR-01.01" not in no_tests_block

    def test_frs_with_stale_verification_section(self, tmp_path: Path):
        """Reference "now" = latest event timestamp (Gemini-H1 determinism fix)."""
        data = ComplianceData(project_root=tmp_path, timestamp="2026-05-21T00:00:00Z")
        data.requirements = [
            RequirementInfo(id="FR-01.01", text="Stale FR", priority="Must", split="01-auth"),
            RequirementInfo(id="FR-01.02", text="Recent FR", priority="Must", split="01-auth"),
        ]
        # FR-01.01 last verified 2026-04-15. FR-01.02 last verified
        # 2026-05-21 (35 days later). Reference-now = max event ts =
        # 2026-05-21. FR-01.01 is 35 days behind → stale.
        data.work_events = [
            WorkEvent(
                id="ev-old", timestamp="2026-04-15T10:00:00Z", source="iterate",
                description="login", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.01"],
            ),
            WorkEvent(
                id="ev-fresh", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="profile", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.02"],
            ),
        ]
        result = generate(data)
        assert "### FRs with stale verification" in result
        stale_block = result.split("### FRs with stale verification")[1].split("###")[0]
        assert "FR-01.01" in stale_block
        # FR-01.02 is the fresh one (matches the reference); not stale.
        assert "FR-01.02" not in stale_block

    def test_frs_with_open_triage_section(self, tmp_path: Path):
        data = self._make_multi_fr_data(tmp_path)
        _seed_open_triage_item(tmp_path, fr_id="FR-01.02")
        result = generate(data)
        assert "### FRs with open triage items" in result
        block = result.split("### FRs with open triage items")[1].split("###")[0]
        assert "FR-01.02" in block
        assert "../agent_docs/triage_inbox.md#trg-" in block

    def test_clean_state_omits_all_three_sections(self, tmp_path: Path):
        """Quiet output when nothing is wrong (audience principle)."""
        data = ComplianceData(project_root=tmp_path, timestamp="2026-05-21T00:00:00Z")
        data.requirements = [
            RequirementInfo(id="FR-01.01", text="Login", priority="Must", split="01-auth"),
        ]
        data.work_events = [WorkEvent(
            id="ev-fresh", timestamp="2026-05-20T10:00:00Z", source="iterate",
            description="login", tests_passed=5, tests_total=5,
            affected_frs=["FR-01.01"],
        )]
        result = generate(data)
        # Coverage Summary section still renders, but the three subsections
        # are absent (no work for the operator).
        assert "## Coverage Summary" in result
        assert "### FRs without tests" not in result
        assert "### FRs with stale verification" not in result
        assert "### FRs with open triage items" not in result

    def test_recent_verification_not_stale(self, tmp_path: Path):
        """An FR verified within 14 days of latest event is NOT listed as stale."""
        data = ComplianceData(project_root=tmp_path, timestamp="2026-05-21T00:00:00Z")
        data.requirements = [
            RequirementInfo(id="FR-01.01", text="Fresh", priority="Must", split="01-auth"),
        ]
        # Two events 3 days apart — second is the reference "now",
        # first is well within the 14-day window.
        data.work_events = [
            WorkEvent(
                id="ev-1", timestamp="2026-05-18T10:00:00Z", source="iterate",
                description="login", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.01"],
            ),
            WorkEvent(
                id="ev-2", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="login follow-up", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.01"],
            ),
        ]
        result = generate(data)
        assert "### FRs with stale verification" not in result

    def test_regeneration_is_deterministic(self, tmp_path: Path):
        """Gemini-H1: two regenerations against the same event log produce
        byte-identical output (the stale window is anchored to the event
        log's latest timestamp, not wall-clock)."""
        data = ComplianceData(project_root=tmp_path, timestamp="2026-05-21T00:00:00Z")
        data.requirements = [
            RequirementInfo(id="FR-01.01", text="Stale", priority="Must", split="01-auth"),
            RequirementInfo(id="FR-01.02", text="Fresh", priority="Must", split="01-auth"),
        ]
        data.work_events = [
            WorkEvent(
                id="ev-old", timestamp="2026-04-15T10:00:00Z", source="iterate",
                description="x", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.01"],
            ),
            WorkEvent(
                id="ev-new", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="y", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.02"],
            ),
        ]
        first = generate(data)
        second = generate(data)
        assert first == second

    def test_iso_timestamp_with_plus_0000_suffix_accepted(self, tmp_path: Path):
        """Code-review-M5: AC-9 accepts both `Z` and `+00:00` suffixes."""
        data = ComplianceData(project_root=tmp_path, timestamp="2026-05-21T00:00:00Z")
        data.requirements = [
            RequirementInfo(id="FR-01.01", text="Stale", priority="Must", split="01-auth"),
            RequirementInfo(id="FR-01.02", text="Fresh", priority="Must", split="01-auth"),
        ]
        # First event ends with `+00:00` (the canonical Python isoformat),
        # second with `Z` (the JSON wire format). Both must parse.
        data.work_events = [
            WorkEvent(
                id="ev-old", timestamp="2026-04-15T10:00:00+00:00", source="iterate",
                description="x", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.01"],
            ),
            WorkEvent(
                id="ev-new", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="y", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.02"],
            ),
        ]
        result = generate(data)
        # The mixed-suffix events parsed successfully — FR-01.01 lands
        # in the stale subsection, FR-01.02 does not.
        stale_block = result.split("### FRs with stale verification")[1].split("###")[0]
        assert "FR-01.01" in stale_block
        assert "FR-01.02" not in stale_block

    def test_malformed_timestamp_warns_and_skips(self, tmp_path: Path):
        """OpenAI-L6 / Gemini-M4: corrupt timestamps emit a warning, row skipped."""
        import warnings
        data = ComplianceData(project_root=tmp_path, timestamp="2026-05-21T00:00:00Z")
        data.requirements = [
            RequirementInfo(id="FR-01.01", text="x", priority="Must", split="01-auth"),
            RequirementInfo(id="FR-01.02", text="y", priority="Must", split="01-auth"),
        ]
        data.work_events = [
            WorkEvent(
                id="ev-bad", timestamp="NOT-AN-ISO-DATE", source="iterate",
                description="x", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.01"],
            ),
            WorkEvent(
                id="ev-good", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="y", tests_passed=5, tests_total=5,
                affected_frs=["FR-01.02"],
            ),
        ]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            generate(data)
        msgs = [str(w.message) for w in caught]
        assert any("NOT-AN-ISO-DATE" in m for m in msgs)


class TestRtmTriageIdValidation:
    """OpenAI-L9 — malformed triage IDs are skipped, not interpolated."""

    def test_malformed_trg_id_is_skipped(self, tmp_path: Path):
        data = _make_data(tmp_path, baseline=0, tests_passed=831, tests_total=831)
        # Hand-craft an item with a bogus id directly via the lower-level API.
        _ensure_triage_on_path()
        import json
        from datetime import datetime, timezone
        triage_log = tmp_path / ".shipwright" / "triage.jsonl"
        triage_log.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        triage_log.write_text(
            json.dumps({"v": 1, "schema": "triage", "created": ts}) + "\n" +
            json.dumps({
                "event": "append", "id": "bogus-id", "ts": ts, "originalTs": ts,
                "source": "test-evidence", "severity": "high", "kind": "bug",
                "title": "x", "detail": "y", "evidencePath": None, "runId": None,
                "commit": None, "dedupKey": None, "launchPayload": None,
                "frId": "FR-01.01", "suiteId": None, "eventId": None,
                "status": "triage",
                "suggestedPriority": "P1", "suggestedDomain": "engineering",
            }) + "\n",
            encoding="utf-8",
        )
        result = generate(data)
        # Status cell does NOT contain a FAIL link with the bogus id.
        rows = [l for l in result.splitlines() if l.startswith("| [FR-01.01]")]
        assert "FAIL → [bogus-id]" not in rows[0]
        # The original COVERED status survives unchanged.
        assert "COVERED" in rows[0]


# ---------------------------------------------------------------------------
# iterate-2026-05-30 — untested (0/0) events are NEUTRAL; an FR's COVERED
# status derives only from the LATEST event that recorded a test count, not
# from `all(...)` over every event ever. (ADR assigned at release.)
#
# Before: status = all(passed==total and total>0 for ev). A single untested
# 0/0 event (docs / refactor / backfill-retro commit, or a verification
# artifact) — or a transient historical failure a later run fixed — pinned
# the FR to FAIL forever even though its latest test run was fully green.
# ---------------------------------------------------------------------------


class TestRtmUntestedEventsNeutral:
    def _data(self, tmp_path: Path, events):
        """events: list of (passed, total, ts) for a single FR-01.01."""
        data = ComplianceData(project_root=tmp_path, timestamp="2026-05-30T00:00:00Z")
        data.requirements = [
            RequirementInfo(id="FR-01.01", text="Login works", priority="Must", split="01-auth"),
        ]
        data.work_events = [
            WorkEvent(
                id=f"ev-{i}", timestamp=ts, source="iterate",
                description=f"work {i}", tests_passed=p, tests_total=t,
                affected_frs=["FR-01.01"],
            )
            for i, (p, t, ts) in enumerate(events)
        ]
        return data

    def _row(self, result: str) -> str:
        rows = [l for l in result.splitlines() if l.startswith("| [FR-01.01]")]
        assert rows, "FR-01.01 row missing"
        return rows[0]

    def test_green_then_untested_event_stays_covered(self, tmp_path: Path):
        """A green run followed by an untested (0/0) commit stays COVERED."""
        data = self._data(tmp_path, [
            (830, 830, "2026-05-14T10:00:00Z"),
            (0, 0, "2026-05-21T10:00:00Z"),   # docs/refactor — no count recorded
        ])
        row = self._row(generate(data))
        assert "COVERED" in row
        assert "FAIL" not in row
        # The untested 0/0 tail must not bleed into the Tests progression cell.
        assert "0/0" not in row

    def test_transient_failure_then_green_is_covered(self, tmp_path: Path):
        """One red test on day 1, fixed fully green on day 2 → COVERED."""
        data = self._data(tmp_path, [
            (1717, 1717, "2026-05-13T10:00:00Z"),
            (1939, 1940, "2026-05-17T10:00:00Z"),  # 1 transient failure
            (1123, 1123, "2026-05-18T10:00:00Z"),  # fixed next day
        ])
        row = self._row(generate(data))
        assert "COVERED" in row
        assert "FAIL" not in row

    def test_latest_tested_uses_timestamp_not_list_order(self, tmp_path: Path):
        """Latest tested event is picked by parsed timestamp, not list order.

        A naive list[-1] would pick the red 5/6 (physically last) → FAIL;
        the chronologically-latest event is the green 10/10 → COVERED.
        """
        data = self._data(tmp_path, [
            (10, 10, "2026-05-20T10:00:00Z"),  # GREEN, latest by ts
            (5, 6, "2026-05-10T10:00:00Z"),    # red, earlier ts, list-last
        ])
        row = self._row(generate(data))
        assert "COVERED" in row
        assert "FAIL" not in row

    def test_latest_failure_after_green_still_fails(self, tmp_path: Path):
        """Guard: a genuine regression in the LATEST tested run is still FAIL."""
        data = self._data(tmp_path, [
            (10, 10, "2026-05-13T10:00:00Z"),
            (5, 6, "2026-05-18T10:00:00Z"),   # latest run is red
        ])
        row = self._row(generate(data))
        assert "FAIL" in row
        assert "COVERED" not in row

    def test_only_untested_events_is_no_tests(self, tmp_path: Path):
        """An FR touched only by untested (0/0) events is NO TESTS, not FAIL."""
        data = self._data(tmp_path, [
            (0, 0, "2026-05-13T10:00:00Z"),
            (0, 0, "2026-05-18T10:00:00Z"),
        ])
        row = self._row(generate(data))
        assert "NO TESTS" in row
        assert "FAIL" not in row

    def test_untested_latest_baseline_still_covered_baseline(self, tmp_path: Path):
        """Baseline path keys off the latest TESTED event, ignoring 0/0 tails."""
        data = self._data(tmp_path, [
            (830, 831, "2026-05-14T10:00:00Z"),  # 1 failure == baseline
            (0, 0, "2026-05-21T10:00:00Z"),      # untested tail
        ])
        data.baseline_failure_count = 1
        row = self._row(generate(data))
        assert "COVERED (baseline)" in row
        assert "| FAIL" not in row

    def test_malformed_timestamp_excluded_from_latest_selection(self, tmp_path: Path):
        """A tested event with an unparseable ts can't win 'latest' selection.

        Robustness mirror of _frs_with_stale_verification: the green event
        with a valid (older) ts is picked over the red event whose ts won't
        parse — so a corrupt timestamp can't silently flip an FR to FAIL.
        """
        import warnings
        data = self._data(tmp_path, [
            (10, 10, "2026-05-10T10:00:00Z"),  # green, parseable
            (5, 6, "not-a-timestamp"),         # red, unparseable → excluded
        ])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            row = self._row(generate(data))
        assert "COVERED" in row
        assert "FAIL" not in row
