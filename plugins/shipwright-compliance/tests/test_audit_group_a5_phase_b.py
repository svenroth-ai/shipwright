"""Group A5.6 — Phase B activation opt-in (``a5_phase_b_activated``).

A5.6 enforces a *dormant-trigger contract*: ``workflow_dispatch:`` must be
active while ``pull_request:`` / ``schedule:`` must NOT be — Phase B
activation (auto-scan on PRs + weekly schedule) must be deliberate, not a
silent default. A project that has *deliberately* activated Phase B (e.g.
shipwright-webui's ``security.yml``, committed activation) had no way to
record that, so A5.6 emitted a permanent LOW false-positive.

This module pins the opt-in: ``a5_phase_b_activated: true`` in the
project-local ``audit_config.json`` waives the *non-dormant-trigger*
sub-case ONLY. The two structural guards — (a) ``workflow_dispatch:``
presence and (b) the bare-``on:``/no-triggers failure — still fire.

Kept in its own file (not appended to ``test_audit_group_a5.py``, which is
an ADR-095 bloat exception) so the new coverage does not ratchet that
exception. Hermetic: each test builds a synthetic workflow under
``tmp_path``.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

# PyYAML is a compliance-plugin dep — same gate as the rest of the A5 suite.
yaml = pytest.importorskip("yaml")

from scripts.audit import group_a5  # noqa: E402
from scripts.audit.audit_adapters import load_shared_lib  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — minimal workflows that vary only the `on:` block
# ---------------------------------------------------------------------------

_ON_PHASE_B = textwrap.dedent(
    """\
    on:
      pull_request:
        branches: [main]
      schedule:
        - cron: '0 6 * * 1'
      workflow_dispatch:
    """
)

_ON_PR_ONLY = textwrap.dedent(
    """\
    on:
      pull_request:
        branches: [main]
      workflow_dispatch:
    """
)

_ON_SCHEDULE_ONLY = textwrap.dedent(
    """\
    on:
      schedule:
        - cron: '0 6 * * 1'
      workflow_dispatch:
    """
)

_ON_DORMANT = textwrap.dedent(
    """\
    on:
      workflow_dispatch:
    """
)

# Phase B triggers active but NO manual handle — structural guard (a).
_ON_NO_DISPATCH = textwrap.dedent(
    """\
    on:
      pull_request:
        branches: [main]
      schedule:
        - cron: '0 6 * * 1'
    """
)

# Bare `on:` — no triggers at all — structural guard (b).
_ON_BARE = "on:\n"


def _workflow(on_block: str) -> str:
    """A minimal-but-valid workflow whose only variable is the `on:` block.

    A5.6 reads `on:` only; the remaining structure just has to parse so the
    run() cascade reaches the A5.6 sub-check (it never stops on A5.3/4/5/7).
    """
    return (
        "name: Security Scan\n\n"
        + on_block
        + textwrap.dedent(
            """\

            permissions:
              contents: read
              actions: read
              security-events: write

            jobs:
              scan:
                runs-on: ubuntu-latest
                steps:
                  - run: echo ok
            """
        )
    )


def _write_workflow(tmp_path: Path, content: str) -> Path:
    target = tmp_path / ".github" / "workflows" / "security.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _a5_6(tmp_path: Path, on_block: str, cfg: dict):
    _write_workflow(tmp_path, _workflow(on_block))
    findings = group_a5.run(tmp_path, cfg, None)
    return next(f for f in findings if f.check_id == "A5.6")


# ---------------------------------------------------------------------------
# Convention default — the new constant lives in security_workflow.py
# ---------------------------------------------------------------------------


def test_security_workflow_declares_phase_b_default_false():
    """The opt-in DEFAULT is a documented convention-lock constant, and it
    is False (dormant-by-default is the safe posture for a fresh repo)."""
    mod = load_shared_lib("security_workflow")
    assert hasattr(mod, "A5_PHASE_B_ACTIVATED_DEFAULT"), (
        "security_workflow.py must declare A5_PHASE_B_ACTIVATED_DEFAULT — "
        "group_a5._load_convention seeds the _Convention default from it."
    )
    assert mod.A5_PHASE_B_ACTIVATED_DEFAULT is False


def test_convention_default_phase_b_is_false():
    """_load_convention seeds a5_phase_b_activated from the constant."""
    conv = group_a5._load_convention()
    assert conv.a5_phase_b_activated is False


# ---------------------------------------------------------------------------
# Phase B activated — the non-dormant sub-case is WAIVED (pass)
# ---------------------------------------------------------------------------


def test_phase_b_activated_waives_active_pull_request(tmp_path):
    a5_6 = _a5_6(tmp_path, _ON_PR_ONLY, {"a5_phase_b_activated": True})
    assert a5_6.status == "pass", a5_6.detail


def test_phase_b_activated_waives_active_schedule(tmp_path):
    a5_6 = _a5_6(tmp_path, _ON_SCHEDULE_ONLY, {"a5_phase_b_activated": True})
    assert a5_6.status == "pass", a5_6.detail


def test_phase_b_activated_waives_both_triggers(tmp_path):
    a5_6 = _a5_6(tmp_path, _ON_PHASE_B, {"a5_phase_b_activated": True})
    assert a5_6.status == "pass", a5_6.detail


def test_phase_b_activated_dormant_still_passes(tmp_path):
    """The flag must not break the ordinary dormant case."""
    a5_6 = _a5_6(tmp_path, _ON_DORMANT, {"a5_phase_b_activated": True})
    assert a5_6.status == "pass", a5_6.detail


# ---------------------------------------------------------------------------
# Phase B activated — structural guards are NOT waived (still fail)
# ---------------------------------------------------------------------------


def test_phase_b_activated_still_fails_missing_workflow_dispatch(tmp_path):
    """Guard (a): even with Phase B on, a workflow with no manual handle
    fails HIGH — the flag only waives the dormant-trigger sub-case."""
    a5_6 = _a5_6(tmp_path, _ON_NO_DISPATCH, {"a5_phase_b_activated": True})
    assert a5_6.status == "fail"
    assert a5_6.severity == "HIGH"
    assert "workflow_dispatch" in a5_6.detail


def test_phase_b_activated_still_fails_bare_on(tmp_path):
    """Guard (b): bare `on:` (no triggers) fails regardless of the flag."""
    a5_6 = _a5_6(tmp_path, _ON_BARE, {"a5_phase_b_activated": True})
    assert a5_6.status == "fail"
    assert a5_6.severity == "HIGH"


# ---------------------------------------------------------------------------
# Default / opt-out behavior is unchanged (regression guards)
# ---------------------------------------------------------------------------


def test_phase_b_default_false_still_fails_active_pull_request(tmp_path):
    """No flag → the existing LOW dormant-contract failure is preserved."""
    a5_6 = _a5_6(tmp_path, _ON_PR_ONLY, {})
    assert a5_6.status == "fail"
    assert a5_6.severity == "LOW"
    assert "non-dormant trigger active" in a5_6.detail


def test_phase_b_explicit_false_still_fails_active_pull_request(tmp_path):
    a5_6 = _a5_6(tmp_path, _ON_PR_ONLY, {"a5_phase_b_activated": False})
    assert a5_6.status == "fail"
    assert a5_6.severity == "LOW"


@pytest.mark.parametrize("bad_value", ["true", 1, "yes", [], {"x": 1}])
def test_phase_b_bad_type_falls_back_to_default(tmp_path, bad_value):
    """Bad-type override (incl. the int-1/bool trap) is ignored — the safe
    dormant-default wins, matching the other a5_* override-safety rules."""
    a5_6 = _a5_6(tmp_path, _ON_PR_ONLY, {"a5_phase_b_activated": bad_value})
    assert a5_6.status == "fail", f"{bad_value!r} should not enable Phase B"
    assert a5_6.severity == "LOW"
