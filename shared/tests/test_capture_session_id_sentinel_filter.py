"""Reader-side sentinel-run filter for the SessionStart Phase-Quality block
(iterate-2026-06-15-sessionstart-sentinel-filter hardening).

Defense-in-depth: ``_findings.md`` is a transient cache regenerated only
on-Stop but consumed at-SessionStart. The writer
(``rewrite_session_findings_summary`` → ``load_actionable_findings``) drops
sentinel-run (``run_id`` in {"", "unknown"}) snapshots so a degenerate audit
context can't drive surfacing. The user-facing SessionStart consumer
(``_build_phase_quality_injection``) applies the SAME canonical predicate
(``is_sentinel_run``) so a stale / not-yet-regenerated digest can't resurface
false Tier-1 FAILs (the cry-wolf failure we observed). The raw parser
(``_collect_tier1_fails``) is deliberately left unfiltered — raw parse vs
actionability policy mirrors the writer's ``load_findings`` vs
``load_actionable_findings`` split. Read-side analogue of
``test_phase_quality_sentinel_rollup_filter.py``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

CAPTURE_SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "capture_session_id.py"
)

_PQ_MARKER = "[Shipwright Phase-Quality]"


def _run(payload: str, **env) -> subprocess.CompletedProcess:
    merged_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, CAPTURE_SCRIPT],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=merged_env,
    )


def _ctx(result: subprocess.CompletedProcess) -> str:
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def _write_digest(project_root: Path, text: str) -> None:
    from lib.phase_quality import SUMMARY_PATH

    path = project_root / SUMMARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


_MIXED_DIGEST = (
    "## adopt — unknown\n"
    "- open FAILs:\n"
    "  - **C1** no phase_completed for adopt\n"
    "\n"
    "## iterate — iterate-2026-06-15-real\n"
    "- open FAILs:\n"
    "  - **W2** something actionable\n"
)


def test_collect_tier1_fails_is_raw_parse_keeps_sentinel():
    """Design pin: the raw parser does NOT filter sentinels — it preserves every
    FAIL with its run id so the caller can apply the actionability policy."""
    from hooks.capture_session_id import _collect_tier1_fails

    fails = _collect_tier1_fails(_MIXED_DIGEST)

    assert {f["id"] for f in fails} == {"C1", "W2"}
    assert {f["run"] for f in fails} == {"unknown", "iterate-2026-06-15-real"}


def test_injection_drops_sentinel_keeps_real(monkeypatch, tmp_path):
    """The consumer drops the sentinel-run FAIL and keeps the real-run one."""
    from hooks.capture_session_id import _build_phase_quality_injection

    _write_digest(tmp_path, _MIXED_DIGEST)
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
    monkeypatch.chdir(tmp_path)

    out = _build_phase_quality_injection(str(tmp_path))

    assert _PQ_MARKER in out
    assert "W2" in out
    assert "C1" not in out
    assert "adopt" not in out


def test_injection_empty_for_sentinel_only_digest(monkeypatch, tmp_path):
    """A digest whose only FAILs are sentinel-run snapshots injects nothing."""
    from hooks.capture_session_id import _build_phase_quality_injection

    _write_digest(
        tmp_path,
        "## adopt — unknown\n- open FAILs:\n  - **C1** no phase_completed\n"
        "## deploy — unknown\n- open FAILs:\n  - **C1** no phase_completed\n",
    )
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
    monkeypatch.chdir(tmp_path)

    assert _build_phase_quality_injection(str(tmp_path)) == ""


def test_injection_keeps_real_run_unchanged(monkeypatch, tmp_path):
    """Control: a non-sentinel digest still surfaces its Tier-1 FAIL (no
    over-filtering / regression of the existing path)."""
    from hooks.capture_session_id import _build_phase_quality_injection

    _write_digest(
        tmp_path,
        "## iterate — run-123\n- open FAILs:\n  - **C1** no phase_completed for x\n",
    )
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
    monkeypatch.chdir(tmp_path)

    out = _build_phase_quality_injection(str(tmp_path))

    assert _PQ_MARKER in out
    assert "C1" in out


def test_phase_quality_block_suppressed_for_sentinel_only_digest(monkeypatch, tmp_path):
    """End-to-end: a stale digest carrying only sentinel-run FAILs must not
    surface the Phase-Quality block at SessionStart (env context still emitted)."""
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    _write_digest(
        tmp_path,
        "## adopt — unknown\n- open FAILs:\n  - **C1** no phase_completed for adopt\n",
    )
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    ctx = _ctx(_run(json.dumps({"session_id": "sentinel-only-sess"})))

    assert _PQ_MARKER not in ctx
    assert "SHIPWRIGHT_PROJECT_ROOT=" in ctx


def test_injection_cap_applied_after_filter_no_starvation(monkeypatch, tmp_path):
    """The 5-FAIL injection cap is applied AFTER the sentinel filter, so a stale
    digest with >5 sentinel FAILs ahead of a real one cannot starve the real
    FAIL out of the budget (would regress if the cap moved back into the parser)."""
    from hooks.capture_session_id import _build_phase_quality_injection

    _write_digest(
        tmp_path,
        "## p1 — unknown\n- open FAILs:\n"
        "  - **A1** s\n  - **A2** s\n  - **A3** s\n"
        "## p2 — unknown\n- open FAILs:\n"
        "  - **A4** s\n  - **A5** s\n  - **A6** s\n"
        "## iterate — iterate-2026-06-15-real\n- open FAILs:\n  - **W2** real one\n",
    )
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
    monkeypatch.chdir(tmp_path)

    out = _build_phase_quality_injection(str(tmp_path))

    assert "W2" in out and "real one" in out
    for sid in ("A1", "A2", "A3", "A4", "A5", "A6"):
        assert sid not in out


def test_injection_caps_nonsentinel_at_five(monkeypatch, tmp_path):
    """R20 (relocated to the consumer): at most 5 Tier-1 FAILs are injected — a
    >5 NON-sentinel digest is capped to the first 5 (coverage that moved out of
    the parser when the cap became a builder-side policy)."""
    from hooks.capture_session_id import _build_phase_quality_injection

    _write_digest(
        tmp_path,
        "## build — run-1\n- open FAILs:\n"
        "  - **W5** a\n  - **W6** b\n  - **W7** c\n"
        "  - **I1** d\n  - **I2** e\n  - **I3** f\n  - **C1** g\n",
    )
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
    monkeypatch.chdir(tmp_path)

    out = _build_phase_quality_injection(str(tmp_path))

    assert _PQ_MARKER in out
    for kept in ("W5", "W6", "W7", "I1", "I2"):
        assert kept in out
    assert "I3" not in out
    assert "C1" not in out
