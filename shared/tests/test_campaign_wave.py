"""Unit tests for `lib.campaign_wave` (campaign-dag-scheduler R5a).

Covers the acceptance criterion: "a test asserting the authorship guard
still refuses under the wave-scoped SHIPWRIGHT_LOOP_UNIT_ID sentinel, and
that _run_id.py/handoff namespacing use the brief-provided unit_id
instead."
"""

from __future__ import annotations

import os

import pytest

from lib import campaign_wave
from lib.campaign_wave import (
    WAVE_UNIT_ID_SENTINEL,
    is_wave_sentinel,
    per_unit_worktree_identity,
    resolve_wave_safe_unit_value,
    write_wave_aware_handoff,
)
from tools import ci_supplychain_authorship_guard as guard


class TestSentinelPredicates:
    def test_sentinel_is_recognised(self):
        assert is_wave_sentinel(WAVE_UNIT_ID_SENTINEL) is True

    def test_a_real_unit_id_is_not_the_sentinel(self):
        for real_id in ("R0", "R5a", "14.2", "section-3"):
            assert is_wave_sentinel(real_id) is False

    def test_none_is_not_the_sentinel(self):
        assert is_wave_sentinel(None) is False

    def test_resolve_wave_safe_unit_value_empties_the_sentinel(self):
        assert resolve_wave_safe_unit_value(WAVE_UNIT_ID_SENTINEL) == ""

    def test_resolve_wave_safe_unit_value_passes_a_real_id_through(self):
        assert resolve_wave_safe_unit_value("R5a") == "R5a"

    def test_no_real_id_can_collide_with_the_sentinel(self):
        """External code review (GLM): `id_charset_ok`'s charset DOES allow
        an underscore mid-string; the collision-proof reason is the
        leading/trailing-separator rejection, not an underscore ban."""
        from lib.campaign_graph import id_charset_ok

        assert id_charset_ok(WAVE_UNIT_ID_SENTINEL) is False


class TestPerUnitWorktreeIdentity:
    """External code review round 2 (glm + openai): `resolve_run_id`'s own
    tier-1 pointer is keyed by `session_id`, which every unit in a wave
    shares — so it is NOT safe under concurrency. The worktree's own
    directory basename is."""

    def test_per_unit_worktree_shape_is_recognised(self, tmp_path):
        wt = tmp_path / "campaign-mydag--R5a"
        wt.mkdir()
        assert per_unit_worktree_identity(wt) == "campaign-mydag--R5a"

    def test_non_per_unit_directory_returns_none(self, tmp_path):
        wt = tmp_path / "some-other-checkout"
        wt.mkdir()
        assert per_unit_worktree_identity(wt) is None

    def test_shared_campaign_worktree_without_unit_suffix_returns_none(self, tmp_path):
        wt = tmp_path / "campaign-mydag"
        wt.mkdir()
        assert per_unit_worktree_identity(wt) is None


class TestAuthorshipGuardStillRefusesUnderTheSentinel:
    """The guard checks TRUTHINESS only — unaffected by the sentinel's value,
    by design (module docstring). Proven directly rather than assumed."""

    def test_guard_refuses_when_the_sentinel_is_set(self, monkeypatch):
        monkeypatch.setenv(guard.CAMPAIGN_RUNNER_ENV_VAR, WAVE_UNIT_ID_SENTINEL)
        with pytest.raises(SystemExit):
            guard.refuse_if_campaign_runner_context()

    def test_guard_allows_when_unset(self, monkeypatch):
        monkeypatch.delenv(guard.CAMPAIGN_RUNNER_ENV_VAR, raising=False)
        guard.refuse_if_campaign_runner_context()  # must not raise


class TestHandoffNamespacingUsesTheRealUnitIdNotTheSentinel:
    def test_real_loop_unit_is_used_verbatim(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        handoff_path = runtime_dir / "session_handoff.md"
        result = write_wave_aware_handoff(
            tmp_path, "sess-1", "content", "loop-1", "R5a", runtime_dir, handoff_path,
        )
        assert result == tmp_path / ".shipwright" / "planning" / "handoffs" / "loop-1" / "R5a.md"
        assert result.read_text(encoding="utf-8") == "content"

    def test_sentinel_falls_back_to_the_resolved_run_id_not_the_literal_sentinel(
        self, tmp_path, monkeypatch,
    ):
        """Two sibling units in the same wave share the identical sentinel
        value — if the namespaced filename ever used it literally, both
        units' handoffs would collide on the SAME file."""
        from lib import phase_quality as pq

        monkeypatch.setattr(pq, "resolve_run_id", lambda project_root, session_id: "iterate-2026-09-23-r5a-x")
        # campaign_wave imports `lib.phase_quality` lazily inside the
        # function under test — patch the module object (ADR-045), which
        # the lazy `from lib import phase_quality as pq` import still sees.
        runtime_dir = tmp_path / "runtime"
        handoff_path = runtime_dir / "session_handoff.md"
        result = write_wave_aware_handoff(
            tmp_path, "sess-1", "content", "loop-1", WAVE_UNIT_ID_SENTINEL, runtime_dir, handoff_path,
        )
        assert WAVE_UNIT_ID_SENTINEL not in result.name
        assert result.name == "iterate-2026-09-23-r5a-x.md"

    def test_two_units_sharing_the_sentinel_resolve_to_distinct_files(self, tmp_path, monkeypatch):
        from lib import phase_quality as pq

        resolved = {"unit-a-root": "iterate-a", "unit-b-root": "iterate-b"}
        monkeypatch.setattr(pq, "resolve_run_id", lambda project_root, session_id: resolved[os.path.basename(str(project_root))])
        wt_a = tmp_path / "unit-a-root"
        wt_b = tmp_path / "unit-b-root"
        wt_a.mkdir()
        wt_b.mkdir()
        runtime_dir = tmp_path / "runtime"
        handoff_path = runtime_dir / "session_handoff.md"
        result_a = write_wave_aware_handoff(
            wt_a, "sess-1", "content-a", "loop-1", WAVE_UNIT_ID_SENTINEL, runtime_dir, handoff_path,
        )
        result_b = write_wave_aware_handoff(
            wt_b, "sess-1", "content-b", "loop-1", WAVE_UNIT_ID_SENTINEL, runtime_dir, handoff_path,
        )
        assert result_a != result_b
        assert result_a.read_text(encoding="utf-8") == "content-a"
        assert result_b.read_text(encoding="utf-8") == "content-b"

    def test_worktree_basename_wins_over_a_colliding_shared_session_pointer(
        self, tmp_path, monkeypatch,
    ):
        """Reproduces the round-2 finding directly: `resolve_run_id` mocked
        to return the SAME value for both units (the real shared-session-
        pointer collision) — the per-unit worktree basename must still keep
        the two handoffs on distinct files, because it is checked FIRST and
        `resolve_run_id` is never even reached."""
        from lib import phase_quality as pq

        monkeypatch.setattr(pq, "resolve_run_id", lambda project_root, session_id: "COLLIDES")
        campaign_root = tmp_path / "worktrees"
        wt_a = campaign_root / "campaign-mydag--R5a"
        wt_b = campaign_root / "campaign-mydag--R5b"
        wt_a.mkdir(parents=True)
        wt_b.mkdir(parents=True)
        runtime_dir = tmp_path / "runtime"
        handoff_path = runtime_dir / "session_handoff.md"
        result_a = write_wave_aware_handoff(
            wt_a, "same-session", "content-a", "loop-1", WAVE_UNIT_ID_SENTINEL, runtime_dir, handoff_path,
        )
        result_b = write_wave_aware_handoff(
            wt_b, "same-session", "content-b", "loop-1", WAVE_UNIT_ID_SENTINEL, runtime_dir, handoff_path,
        )
        assert result_a != result_b
        assert "COLLIDES" not in result_a.name
        assert "COLLIDES" not in result_b.name
        assert result_a.read_text(encoding="utf-8") == "content-a"
        assert result_b.read_text(encoding="utf-8") == "content-b"

    def test_no_loop_context_writes_the_plain_runtime_path(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        handoff_path = runtime_dir / "session_handoff.md"
        result = write_wave_aware_handoff(
            tmp_path, "sess-1", "content", None, None, runtime_dir, handoff_path,
        )
        assert result == handoff_path
        assert result.read_text(encoding="utf-8") == "content"


class TestRunIdTier3IgnoresTheSentinel:
    def test_resolve_run_id_falls_back_to_loop_id_alone_under_the_sentinel(self, tmp_path, monkeypatch):
        from lib.phase_quality._run_id import resolve_run_id

        monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
        monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", WAVE_UNIT_ID_SENTINEL)
        # No pointer, no run_config, no events -- forces tier 3.
        result = resolve_run_id(tmp_path, "sess-1")
        assert result == "loop-1"
        assert WAVE_UNIT_ID_SENTINEL not in result

    def test_resolve_run_id_still_composes_a_real_loop_unit(self, tmp_path, monkeypatch):
        from lib.phase_quality._run_id import resolve_run_id

        monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
        monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "section-3")
        result = resolve_run_id(tmp_path, "sess-1")
        assert result == "loop-1-section-3"

    def test_resolve_run_id_prefers_the_per_unit_worktree_over_loop_id_alone(
        self, tmp_path, monkeypatch,
    ):
        """A per-unit worktree gets its OWN composed id under the sentinel,
        not the shared `loop_id`-alone value two sibling units would
        otherwise collide on."""
        from lib.phase_quality._run_id import resolve_run_id

        wt = tmp_path / "campaign-mydag--R5a"
        wt.mkdir()
        monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
        monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", WAVE_UNIT_ID_SENTINEL)
        result = resolve_run_id(wt, "sess-1")
        assert result == "loop-1-campaign-mydag--R5a"


def test_all_exports_present():
    for name in campaign_wave.__all__:
        assert hasattr(campaign_wave, name)
