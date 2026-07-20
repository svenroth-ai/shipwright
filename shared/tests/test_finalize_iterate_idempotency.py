"""Dashboard-render idempotency for shared/scripts/tools/finalize_iterate.py.

Split out of ``test_finalize_iterate.py`` (an ADR-096 size exception) so the
idempotency cluster — the helper plus the two render tests — has its own
sub-300-LOC home rather than ratcheting the exception file larger. Sibling of
``test_finalize_iterate_utf8.py``, which follows the same convention.

The subject: two ``finalize_iterate.run`` calls must render a byte-identical
dashboard *body*. The one legitimately-varying token is the wall-clock minute
in the ``> Updated:`` banner — each run appends a fresh ``grade_snapshot`` event
during compliance regen, so ``latest_event_dt`` (and thus the banner minute)
advances between runs. Comparing the full byte-string flaked whenever the two
runs straddled a minute boundary (trg-183a304a).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Mirrors test_finalize_iterate.py: the FR-gate needs a valid classification on
# every run() that writes an event; the minimal tooling classification keeps
# these dashboard-idempotency tests focused while satisfying the gate.
_VALID_EXTRAS = {
    "change_type": "tooling",
    "none_reason": "finalize unit test classification",
}


@pytest.fixture()
def project(tmp_path):
    """Create a minimal project layout."""
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}),
        encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    return tmp_path


def _dashboard_body_and_banner_suffix(dashboard: str) -> tuple[str, str]:
    """Split a rendered dashboard into ``(body, banner_suffix)``.

    The ``> Updated: {now} | Session: ...`` banner is the ONLY line whose
    content is wall-clock derived: ``now`` is a minute-resolution UTC stamp
    from ``latest_event_dt`` (the most recent event in the log). Every
    ``finalize_iterate.run`` appends a fresh ``grade_snapshot`` event during
    its compliance-regen step, so ``latest_event_dt`` — and therefore the
    banner minute — legitimately advances between two runs. Comparing the
    full byte-string then flakes whenever the two runs straddle a minute
    boundary (trg-183a304a). The dashboard *body* is day-resolution /
    content-derived and must be byte-identical across runs.

    Returns the body (banner line removed) plus the banner text from
    ``| Session:`` onward (Session + Run — both wall-clock independent), so a
    caller can assert idempotency of everything except the minute stamp.
    """
    lines = dashboard.splitlines()
    banner_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("> Updated:")), None
    )
    assert banner_idx is not None, "dashboard render is missing its '> Updated:' banner"
    banner = lines[banner_idx]
    body = "\n".join(lines[:banner_idx] + lines[banner_idx + 1:])
    _, _, suffix = banner.partition("| Session:")
    return body, suffix


def test_run_is_idempotent(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result1 = run(project, run_id="test-005", event_extras=_VALID_EXTRAS)
    dashboard1 = (project / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")

    result2 = run(project, run_id="test-005", event_extras=_VALID_EXTRAS)
    dashboard2 = (project / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")

    # Idempotency is asserted over everything EXCEPT the wall-clock minute in
    # the "> Updated:" banner. Each finalize appends a fresh grade_snapshot
    # event, so latest_event_dt (and thus the banner minute) legitimately
    # advances between runs; a full byte comparison made this test flake
    # whenever the two runs straddled a minute boundary (trg-183a304a). The
    # body plus the Session/Run banner suffix are what must be identical.
    body1, suffix1 = _dashboard_body_and_banner_suffix(dashboard1)
    body2, suffix2 = _dashboard_body_and_banner_suffix(dashboard2)
    assert body1 == body2
    assert suffix1 == suffix2
    assert result1["steps"]["dashboard"].get("written")
    assert result2["steps"]["dashboard"].get("written")


def test_run_is_idempotent_even_when_banner_minute_advances(project, monkeypatch):
    """Deterministic reproduction of the trg-183a304a flake.

    Forces the two finalize renders to stamp banner minutes one minute apart
    (as a real minute-boundary straddle would). The full byte-strings then
    differ — the exact flake that reddened unrelated PRs — while the body and
    the Session/Run banner suffix stay identical, which is the property the
    idempotency assertion must measure. A regression that leaked wall-clock
    into the body (or dropped the banner) would fail here.
    """
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run
    import tools.update_build_dashboard as ubd

    # `_deterministic_now` is called exactly once per render (once per run),
    # so a two-value iterator forces a one-minute drift between the two runs.
    minutes = iter(["2026-07-20 21:20 UTC", "2026-07-20 21:21 UTC"])
    monkeypatch.setattr(ubd, "_deterministic_now", lambda _project_root: next(minutes))

    run(project, run_id="test-drift", event_extras=_VALID_EXTRAS)
    dashboard1 = (project / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")
    run(project, run_id="test-drift", event_extras=_VALID_EXTRAS)
    dashboard2 = (project / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")

    # The naive full-byte comparison WOULD fail here — this is the flake.
    assert dashboard1 != dashboard2
    # ...but the render is idempotent once the wall-clock minute is excluded.
    body1, suffix1 = _dashboard_body_and_banner_suffix(dashboard1)
    body2, suffix2 = _dashboard_body_and_banner_suffix(dashboard2)
    assert body1 == body2
    assert suffix1 == suffix2
