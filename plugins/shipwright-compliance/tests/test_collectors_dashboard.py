"""Tests for the Compliance Dashboard bloat-findings column (B3).

Campaign B B3 wired three Quality-Indicators rows into
``compliance_report.py`` fed from
``shared.scripts.lib.phase_quality.collect_bloat_summary``. Covers
producer behaviour (over_limit / in_allowlist / ratchet_delta math +
fail-open) plus the spec-mandated round-trip probe (regenerate the
dashboard MD against a fixture; confirm all three rows appear).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Load shared phase_quality as a top-level package (not `lib.phase_quality`).
# test_enforcement_hooks.py defensively clears its own `lib.*` cache before
# resolving `lib.thresholds`, tolerating the `lib.*` entries this import populates.
_SHARED_LIB = str(Path(__file__).resolve().parents[3] / "shared" / "scripts" / "lib")
if _SHARED_LIB not in sys.path:
    sys.path.insert(0, _SHARED_LIB)
from phase_quality import collect_bloat_summary  # noqa: E402

from scripts.lib.compliance_report import generate, generate_file  # noqa: E402
from scripts.lib.data_collector import ComplianceData  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_baseline(project_root: Path, entries: list[dict]) -> Path:
    """Write a ``shipwright_bloat_baseline.json`` fixture and return its path."""
    target = project_root / "shipwright_bloat_baseline.json"
    target.write_text(
        json.dumps({"version": 1, "entries": entries}, indent=2),
        encoding="utf-8",
    )
    return target


def _write_file(project_root: Path, rel: str, lines: int) -> Path:
    """Create a fake source file with ``lines`` newlines under the project."""
    path = project_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join([f"# line {i}" for i in range(lines)]) + "\n"
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Producer — collect_bloat_summary
# ---------------------------------------------------------------------------

class TestCollectBloatSummary:
    def test_no_baseline_returns_zeros(self, tmp_path: Path) -> None:
        result = collect_bloat_summary(tmp_path)
        assert result == {"over_limit": 0, "in_allowlist": 0, "ratchet_delta": 0}

    def test_malformed_baseline_returns_zeros(self, tmp_path: Path) -> None:
        (tmp_path / "shipwright_bloat_baseline.json").write_text(
            "{not json", encoding="utf-8",
        )
        result = collect_bloat_summary(tmp_path)
        assert result == {"over_limit": 0, "in_allowlist": 0, "ratchet_delta": 0}

    def test_grandfathered_entry_under_current_is_negative_delta(
        self, tmp_path: Path,
    ) -> None:
        # File shrank from 500 to 250 newlines: measured (250) < current (500).
        _write_baseline(tmp_path, [{
            "path": "src/big.py", "limit": 300, "current": 500,
            "state": "grandfathered", "adr": None,
        }])
        _write_file(tmp_path, "src/big.py", 250)

        result = collect_bloat_summary(tmp_path)
        # in_allowlist counts grandfathered.
        assert result["in_allowlist"] == 1
        # over_limit==0 because 250 <= limit (300).
        assert result["over_limit"] == 0
        # ratchet_delta = 250 - 500 = -250 (shrinking surface, good).
        assert result["ratchet_delta"] == -250

    def test_grandfathered_entry_above_limit_counts_in_over_limit(
        self, tmp_path: Path,
    ) -> None:
        # File still at 500 newlines, limit 300: over_limit fires.
        _write_baseline(tmp_path, [{
            "path": "src/big.py", "limit": 300, "current": 500,
            "state": "grandfathered", "adr": None,
        }])
        _write_file(tmp_path, "src/big.py", 500)

        result = collect_bloat_summary(tmp_path)
        assert result["over_limit"] == 1
        assert result["in_allowlist"] == 1
        # measured (500) - current (500) = 0 — no ratchet but still over limit.
        assert result["ratchet_delta"] == 0

    def test_exception_state_excluded_from_over_limit(self, tmp_path: Path) -> None:
        # ADR-justified exception: counts in_allowlist, excluded from over_limit.
        _write_baseline(tmp_path, [{
            "path": "src/big.py", "limit": 300, "current": 500,
            "state": "exception",
            "adr": ".shipwright/planning/adr/099-big-exception.md",
        }])
        _write_file(tmp_path, "src/big.py", 500)

        result = collect_bloat_summary(tmp_path)
        assert result["over_limit"] == 0
        assert result["in_allowlist"] == 1
        # exception entries do NOT contribute to ratchet_delta either
        # (only state=grandfathered does).
        assert result["ratchet_delta"] == 0

    def test_ratchet_delta_positive_when_file_grew(self, tmp_path: Path) -> None:
        # File grew from baseline 500 to 520 — Iron Law violation surfaces
        # as a positive ratchet_delta.
        _write_baseline(tmp_path, [{
            "path": "src/big.py", "limit": 300, "current": 500,
            "state": "grandfathered", "adr": None,
        }])
        _write_file(tmp_path, "src/big.py", 520)

        result = collect_bloat_summary(tmp_path)
        assert result["ratchet_delta"] == 20
        assert result["over_limit"] == 1

    def test_missing_worktree_file_is_zero_contribution(self, tmp_path: Path) -> None:
        # Baseline entry exists but file deleted from disk: stale, not
        # ratcheting. Counts in_allowlist but 0 over_limit + 0 delta.
        _write_baseline(tmp_path, [{
            "path": "src/gone.py", "limit": 300, "current": 500,
            "state": "grandfathered", "adr": None,
        }])
        # Note: NO _write_file call — file absent.

        result = collect_bloat_summary(tmp_path)
        assert result["in_allowlist"] == 1
        assert result["over_limit"] == 0
        assert result["ratchet_delta"] == 0

    def test_mixed_entries_aggregate_correctly(self, tmp_path: Path) -> None:
        _write_baseline(tmp_path, [
            {"path": "a.py", "limit": 300, "current": 400,
             "state": "grandfathered", "adr": None},     # 350 > limit (300) → over
            {"path": "b.py", "limit": 300, "current": 500,
             "state": "grandfathered", "adr": None},     # 550 > limit + ratchet
            {"path": "c.py", "limit": 300, "current": 600,
             "state": "exception",
             "adr": ".shipwright/planning/adr/077.md"},   # excluded from over_limit
        ])
        _write_file(tmp_path, "a.py", 350)
        _write_file(tmp_path, "b.py", 550)
        _write_file(tmp_path, "c.py", 700)

        result = collect_bloat_summary(tmp_path)
        # Two grandfathered + one exception = 3 in_allowlist.
        assert result["in_allowlist"] == 3
        # a + b both over their limit; c is an exception → excluded.
        assert result["over_limit"] == 2
        # delta = (350-400) + (550-500) = -50 + 50 = 0; c excluded.
        assert result["ratchet_delta"] == 0


# ---------------------------------------------------------------------------
# Consumer — Compliance Dashboard renders the three rows
# ---------------------------------------------------------------------------

class TestDashboardRendersBloatRows:
    def _minimal_data(self, project_root: Path) -> ComplianceData:
        return ComplianceData(
            project_root=project_root,
            configs={"run": {"profile": "test", "scope": "library"}},
            timestamp="2026-05-25T00:00:00Z",
        )

    def test_legacy_mode_renders_all_three_bloat_rows(self, tmp_path: Path) -> None:
        # No baseline → all three rows render with zeros.
        data = self._minimal_data(tmp_path)
        md = generate(data)
        assert "| Bloat over-limit (grandfathered) | 0 |" in md
        assert "| Bloat in allowlist | 0 entries |" in md
        assert "| Bloat ratchet delta | +0 lines |" in md

    def test_legacy_mode_over_limit_is_info_not_warn(self, tmp_path: Path) -> None:
        # Grandfathering IS the acceptance → over-limit is INFO, never WARN. The
        # ratchet delta carries the real signal (regression) and stays WARN.
        _write_baseline(tmp_path, [{
            "path": "src/big.py", "limit": 300, "current": 500,
            "state": "grandfathered", "adr": None,
        }])
        _write_file(tmp_path, "src/big.py", 600)
        md = generate(self._minimal_data(tmp_path))
        assert "| Bloat over-limit (grandfathered) | 1 | INFO" in md
        assert "| Bloat ratchet delta | +100 lines | WARN" in md

    def test_legacy_mode_clean_baseline_passes(self, tmp_path: Path) -> None:
        # Campaign B goal: post-campaign, every grandfathered entry
        # should be measured <= current. Over-limit is INFO; ratchet PASS.
        _write_baseline(tmp_path, [{
            "path": "src/big.py", "limit": 300, "current": 500,
            "state": "grandfathered", "adr": None,
        }])
        _write_file(tmp_path, "src/big.py", 280)  # below limit, shrunk

        data = self._minimal_data(tmp_path)
        md = generate(data)
        assert "| Bloat over-limit (grandfathered) | 0 | INFO" in md
        assert "| Bloat ratchet delta | -220 lines | PASS" in md

    def test_events_mode_renders_bloat_rows(self, tmp_path: Path) -> None:
        # Events-mode triggers when work_events is non-empty. Reuse the
        # event-shape from test_compliance_report.py's fixtures by
        # constructing a minimal WorkEvent directly.
        from scripts.lib.data_collector import WorkEvent

        _write_baseline(tmp_path, [{
            "path": "src/big.py", "limit": 300, "current": 500,
            "state": "grandfathered", "adr": None,
        }])
        _write_file(tmp_path, "src/big.py", 510)

        data = self._minimal_data(tmp_path)
        data.work_events = [WorkEvent(
            id="evt-1", timestamp="2026-05-25T00:00:00Z", source="iterate",
            commit="abc", tests_passed=1, tests_total=1,
        )]
        md = generate(data)
        # Events-mode also renders the column (proves the integration on
        # both branches of _quality_indicators_*).
        assert "| Bloat over-limit (grandfathered) | 1 | INFO" in md
        assert "| Bloat in allowlist | 1 entries | INFO" in md
        assert "| Bloat ratchet delta | +10 lines | WARN" in md


# ---------------------------------------------------------------------------
# Round-trip probe — generate_file writes the new column to disk (spec-mandated)
# ---------------------------------------------------------------------------

class TestRoundTripDashboardMd:
    def test_generate_file_writes_bloat_rows_to_dashboard_md(
        self, tmp_path: Path,
    ) -> None:
        _write_baseline(tmp_path, [
            {"path": "src/big.py", "limit": 300, "current": 500,
             "state": "grandfathered", "adr": None},
            {"path": "src/exc.py", "limit": 300, "current": 600,
             "state": "exception",
             "adr": ".shipwright/planning/adr/077.md"},
        ])
        _write_file(tmp_path, "src/big.py", 450)  # shrunk; under current
        _write_file(tmp_path, "src/exc.py", 700)  # over limit but exception

        # Provide a minimal ComplianceData so generate_file doesn't try to
        # call collect_all (which would walk an empty fixture tree).
        data = ComplianceData(
            project_root=tmp_path,
            configs={"run": {"profile": "test", "scope": "library"}},
            timestamp="2026-05-25T00:00:00Z",
        )
        output = generate_file(tmp_path, data)

        assert output.exists()
        rendered = output.read_text(encoding="utf-8")
        # Three rows present.
        assert "Bloat over-limit" in rendered
        assert "Bloat in allowlist" in rendered
        assert "Bloat ratchet delta" in rendered
        # in_allowlist=2 (1 grandfathered + 1 exception); over_limit=1
        # (big.py 450 > limit 300; exc excluded); delta=-50 (shrinking).
        assert "| Bloat in allowlist | 2 entries |" in rendered
        assert "| Bloat over-limit (grandfathered) | 1 | INFO" in rendered
        assert "| Bloat ratchet delta | -50 lines | PASS" in rendered


# ---------------------------------------------------------------------------
# Cross-import probe — phase_quality.collect_bloat_summary IS the surface
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", [
    "collect_bloat_summary",
    "is_shipwright_project",
    "phase_from_plugin_root",
    "run_canon_checks",
    "write_finding_json",
    "regenerate_all_aggregates",
])
def test_phase_quality_public_surface_re_exports(symbol: str) -> None:
    """Public surface preserved post-split: every pre-split symbol is
    still importable from ``lib.phase_quality`` directly."""
    from lib import phase_quality

    assert hasattr(phase_quality, symbol), (
        f"phase_quality.{symbol} missing — B3 split broke the public surface"
    )
