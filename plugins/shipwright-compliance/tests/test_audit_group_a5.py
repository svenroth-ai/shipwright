"""Group A5 — CI security workflow integrity (post-Plan-v7 follow-up).

A5 audits ``.github/workflows/security.yml`` against the convention-lock
constants in ``shared/scripts/lib/security_workflow.py``:

- A5.1: skip cleanly when the workflow file is absent
- A5.2: fail with parse-error detail when YAML is malformed
- A5.3: fail when ``permissions:`` block is missing or any
  ``REQUIRED_PERMISSIONS`` key is missing/wrong
- A5.4: fail when no step carries ``id: <CRITICAL_GATE_STEP_ID>``
- A5.5: fail when no step ``uses:`` the canonical SARIF upload action,
  OR when its ``category:`` does not match ``SARIF_CATEGORY``
- A5.6: fail when ``workflow_dispatch:`` is absent OR when active
  ``pull_request:`` / ``schedule:`` triggers are present (Phase B
  activation must be deliberate)
- A5.7: fail when the SARIF upload step lacks a fork-PR guard
  (``head.repo.full_name == github.repository`` substring)
- A5.8: every Finding carries ``source=detective-only`` and ``group="A"``
- A5.9: a crash inside one sub-check produces a fail Finding without
  suppressing other sub-checks

Hermetic: every test builds a synthetic workflow under ``tmp_path``.
Mirrors the existing ``test_audit_groups_a_d.py`` fixture shape.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

# PyYAML is a compliance-plugin dep — same gate as the SSoT drift test.
yaml = pytest.importorskip("yaml")

from scripts.audit import group_a5  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def _canonical_workflow() -> str:
    """A workflow that satisfies every A5 sub-check.

    Built from the convention-lock contract — keeps the test independent
    from the on-disk template (the SSoT drift test pins the template
    against the same constants in shared/tests/).
    """
    return textwrap.dedent(
        """
        name: Security Scan

        on:
          # pull_request:
          #   branches: [main]
          # schedule:
          #   - cron: '0 6 * * 1'
          workflow_dispatch:

        permissions:
          contents: read
          actions: read
          security-events: write
          pull-requests: write

        jobs:
          scan:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - name: Upload SARIF
                if: always() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)
                uses: github/codeql-action/upload-sarif@v3
                with:
                  sarif_file: sarif
                  category: shipwright-security
              - name: Check for critical findings
                id: shipwright-critical-gate
                shell: bash
                run: echo ok
        """
    ).lstrip("\n")


def _write_workflow(tmp_path: Path, content: str) -> Path:
    target = tmp_path / ".github" / "workflows" / "security.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# A5.1 — skip when workflow file absent
# ---------------------------------------------------------------------------


def test_a5_1_skips_when_workflow_file_absent(tmp_path):
    findings = group_a5.run(tmp_path, {}, None)
    assert len(findings) == 1, [f.check_id for f in findings]
    f = findings[0]
    assert f.check_id == "A5.1"
    assert f.status == "skip"
    assert "no GitHub Actions workflow" in f.detail
    assert f.group == "A"
    assert f.source == SOURCE_DETECTIVE_ONLY


# ---------------------------------------------------------------------------
# A5.2 — fail when YAML is malformed
# ---------------------------------------------------------------------------


def test_a5_2_fails_on_malformed_yaml(tmp_path):
    _write_workflow(tmp_path, "permissions:\n  contents: read\n    actions: read\n")
    findings = group_a5.run(tmp_path, {}, None)
    by_id = {f.check_id: f for f in findings}
    assert "A5.2" in by_id
    a5_2 = by_id["A5.2"]
    assert a5_2.status == "fail"
    assert a5_2.severity == "HIGH"
    # No structural checks should have been attempted after parse failed.
    assert "A5.3" not in by_id
    assert "A5.4" not in by_id


def test_a5_2_passes_on_well_formed_yaml(tmp_path):
    _write_workflow(tmp_path, _canonical_workflow())
    findings = group_a5.run(tmp_path, {}, None)
    by_id = {f.check_id: f for f in findings}
    assert "A5.2" in by_id
    assert by_id["A5.2"].status == "pass"


# ---------------------------------------------------------------------------
# A5.3 — permissions block matches REQUIRED_PERMISSIONS
# ---------------------------------------------------------------------------


def test_a5_3_passes_with_required_permissions_present(tmp_path):
    _write_workflow(tmp_path, _canonical_workflow())
    findings = group_a5.run(tmp_path, {}, None)
    a5_3 = next(f for f in findings if f.check_id == "A5.3")
    assert a5_3.status == "pass", a5_3.detail


def test_a5_3_fails_when_security_events_missing(tmp_path):
    bad = _canonical_workflow().replace(
        "  security-events: write\n", "",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_3 = next(f for f in findings if f.check_id == "A5.3")
    assert a5_3.status == "fail"
    assert a5_3.severity == "HIGH"
    assert "security-events" in a5_3.detail


def test_a5_3_fails_when_permissions_block_absent(tmp_path):
    bad = _canonical_workflow().replace(
        "permissions:\n"
        "  contents: read\n"
        "  actions: read\n"
        "  security-events: write\n"
        "  pull-requests: write\n\n",
        "",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_3 = next(f for f in findings if f.check_id == "A5.3")
    assert a5_3.status == "fail"
    assert a5_3.severity == "HIGH"


def test_a5_3_fails_when_permissions_block_is_null(tmp_path):
    """Null `permissions:` is treated as missing block — once *any* explicit
    permissions key is set GitHub falls back unlisted to none, and a null
    block is functionally the same edge case for audit purposes."""
    bad = _canonical_workflow().replace(
        "permissions:\n"
        "  contents: read\n"
        "  actions: read\n"
        "  security-events: write\n"
        "  pull-requests: write\n",
        "permissions:\n",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_3 = next(f for f in findings if f.check_id == "A5.3")
    assert a5_3.status == "fail"


def test_a5_3_passes_when_extra_optional_permission_present(tmp_path):
    """`pull-requests: write` is in OPTIONAL_PERMISSIONS — its presence
    must not fail the check. Only REQUIRED_PERMISSIONS keys are mandatory."""
    _write_workflow(tmp_path, _canonical_workflow())  # has pull-requests
    findings = group_a5.run(tmp_path, {}, None)
    a5_3 = next(f for f in findings if f.check_id == "A5.3")
    assert a5_3.status == "pass", a5_3.detail


# ---------------------------------------------------------------------------
# A5.4 — critical-gate step id present
# ---------------------------------------------------------------------------


def test_a5_4_passes_when_gate_id_present(tmp_path):
    _write_workflow(tmp_path, _canonical_workflow())
    findings = group_a5.run(tmp_path, {}, None)
    a5_4 = next(f for f in findings if f.check_id == "A5.4")
    assert a5_4.status == "pass", a5_4.detail


def test_a5_4_fails_when_gate_step_lacks_canonical_id(tmp_path):
    bad = _canonical_workflow().replace(
        "        id: shipwright-critical-gate\n", "",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_4 = next(f for f in findings if f.check_id == "A5.4")
    assert a5_4.status == "fail"
    assert a5_4.severity == "HIGH"
    assert "shipwright-critical-gate" in a5_4.detail


# ---------------------------------------------------------------------------
# A5.5 — SARIF upload step present + canonical category
# ---------------------------------------------------------------------------


def test_a5_5_passes_with_canonical_action_and_category(tmp_path):
    _write_workflow(tmp_path, _canonical_workflow())
    findings = group_a5.run(tmp_path, {}, None)
    a5_5 = next(f for f in findings if f.check_id == "A5.5")
    assert a5_5.status == "pass", a5_5.detail


def test_a5_5_fails_when_sarif_upload_step_absent(tmp_path):
    bad = _canonical_workflow().replace(
        "      - name: Upload SARIF\n"
        "        if: always() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)\n"
        "        uses: github/codeql-action/upload-sarif@v3\n"
        "        with:\n"
        "          sarif_file: sarif\n"
        "          category: shipwright-security\n",
        "",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_5 = next(f for f in findings if f.check_id == "A5.5")
    assert a5_5.status == "fail"
    assert a5_5.severity == "MEDIUM"


def test_a5_5_fails_when_sarif_category_mismatched(tmp_path):
    bad = _canonical_workflow().replace(
        "category: shipwright-security",
        "category: foo-bucket",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_5 = next(f for f in findings if f.check_id == "A5.5")
    assert a5_5.status == "fail"
    assert a5_5.severity == "MEDIUM"
    assert "shipwright-security" in a5_5.detail


def test_a5_5_accepts_versioned_action_pin(tmp_path):
    """Bumping ``@v3`` to ``@v4`` must not break A5 — the prefix match
    is version-agnostic."""
    bumped = _canonical_workflow().replace(
        "uses: github/codeql-action/upload-sarif@v3",
        "uses: github/codeql-action/upload-sarif@v4",
    )
    _write_workflow(tmp_path, bumped)
    findings = group_a5.run(tmp_path, {}, None)
    a5_5 = next(f for f in findings if f.check_id == "A5.5")
    assert a5_5.status == "pass", a5_5.detail


# ---------------------------------------------------------------------------
# A5.6 — dormant-trigger contract
# ---------------------------------------------------------------------------


def test_a5_6_passes_with_dormant_triggers(tmp_path):
    _write_workflow(tmp_path, _canonical_workflow())
    findings = group_a5.run(tmp_path, {}, None)
    a5_6 = next(f for f in findings if f.check_id == "A5.6")
    assert a5_6.status == "pass", a5_6.detail


def test_a5_6_fails_when_workflow_dispatch_missing(tmp_path):
    bad = _canonical_workflow().replace("  workflow_dispatch:\n", "")
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_6 = next(f for f in findings if f.check_id == "A5.6")
    assert a5_6.status == "fail"
    assert a5_6.severity == "HIGH"
    assert "workflow_dispatch" in a5_6.detail


def test_a5_6_fails_when_pull_request_trigger_active(tmp_path):
    bad = _canonical_workflow().replace(
        "  # pull_request:\n  #   branches: [main]\n",
        "  pull_request:\n    branches: [main]\n",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_6 = next(f for f in findings if f.check_id == "A5.6")
    assert a5_6.status == "fail"
    assert a5_6.severity == "LOW"
    assert "pull_request" in a5_6.detail


def test_a5_6_fails_when_schedule_trigger_active(tmp_path):
    bad = _canonical_workflow().replace(
        "  # schedule:\n  #   - cron: '0 6 * * 1'\n",
        "  schedule:\n    - cron: '0 6 * * 1'\n",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_6 = next(f for f in findings if f.check_id == "A5.6")
    assert a5_6.status == "fail"
    assert a5_6.severity == "LOW"
    assert "schedule" in a5_6.detail


def test_a5_6_passes_when_on_is_scalar_workflow_dispatch(tmp_path):
    """``on: workflow_dispatch`` (scalar form) is legal GitHub Actions —
    A5.6 must accept it. Reviewer-flagged edge case."""
    scalar = _canonical_workflow().replace(
        "on:\n"
        "  # pull_request:\n"
        "  #   branches: [main]\n"
        "  # schedule:\n"
        "  #   - cron: '0 6 * * 1'\n"
        "  workflow_dispatch:\n",
        "on: workflow_dispatch\n",
    )
    _write_workflow(tmp_path, scalar)
    findings = group_a5.run(tmp_path, {}, None)
    a5_6 = next(f for f in findings if f.check_id == "A5.6")
    assert a5_6.status == "pass", a5_6.detail


def test_a5_6_passes_when_on_is_list_with_workflow_dispatch(tmp_path):
    """``on: [workflow_dispatch, push]`` (list form) is legal —
    A5.6 must accept it."""
    listform = _canonical_workflow().replace(
        "on:\n"
        "  # pull_request:\n"
        "  #   branches: [main]\n"
        "  # schedule:\n"
        "  #   - cron: '0 6 * * 1'\n"
        "  workflow_dispatch:\n",
        "on: [workflow_dispatch]\n",
    )
    _write_workflow(tmp_path, listform)
    findings = group_a5.run(tmp_path, {}, None)
    a5_6 = next(f for f in findings if f.check_id == "A5.6")
    assert a5_6.status == "pass", a5_6.detail


# ---------------------------------------------------------------------------
# A5.7 — fork-PR guard wired
# ---------------------------------------------------------------------------


def test_a5_7_passes_with_canonical_fork_guard(tmp_path):
    _write_workflow(tmp_path, _canonical_workflow())
    findings = group_a5.run(tmp_path, {}, None)
    a5_7 = next(f for f in findings if f.check_id == "A5.7")
    assert a5_7.status == "pass", a5_7.detail


def test_a5_7_fails_when_upload_step_lacks_fork_guard(tmp_path):
    bad = _canonical_workflow().replace(
        "        if: always() && (github.event_name != 'pull_request' "
        "|| github.event.pull_request.head.repo.full_name == github.repository)\n",
        "",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_7 = next(f for f in findings if f.check_id == "A5.7")
    assert a5_7.status == "fail"
    assert a5_7.severity == "MEDIUM"


def test_a5_7_passes_when_fork_guard_uses_template_expr(tmp_path):
    """Both ``${{ ... }}`` wrapped and unwrapped expressions are legal."""
    wrapped = _canonical_workflow().replace(
        "        if: always() && (github.event_name != 'pull_request' "
        "|| github.event.pull_request.head.repo.full_name == github.repository)\n",
        "        if: ${{ always() && (github.event_name != 'pull_request' "
        "|| github.event.pull_request.head.repo.full_name == github.repository) }}\n",
    )
    _write_workflow(tmp_path, wrapped)
    findings = group_a5.run(tmp_path, {}, None)
    a5_7 = next(f for f in findings if f.check_id == "A5.7")
    assert a5_7.status == "pass", a5_7.detail


def test_a5_7_skips_when_no_upload_step(tmp_path):
    """A5.5 already failed on the absent upload step — A5.7 has nothing to
    inspect, so it skips rather than producing a redundant fail."""
    bad = _canonical_workflow().replace(
        "      - name: Upload SARIF\n"
        "        if: always() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)\n"
        "        uses: github/codeql-action/upload-sarif@v3\n"
        "        with:\n"
        "          sarif_file: sarif\n"
        "          category: shipwright-security\n",
        "",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_7 = next(f for f in findings if f.check_id == "A5.7")
    assert a5_7.status == "skip"
    detail_lower = a5_7.detail.lower()
    assert "no sarif upload step" in detail_lower or \
           "no upload" in detail_lower, a5_7.detail


# ---------------------------------------------------------------------------
# A5.8 — Finding metadata contract
# ---------------------------------------------------------------------------


def test_a5_findings_carry_detective_only_source_and_group_a(tmp_path):
    _write_workflow(tmp_path, _canonical_workflow())
    findings = group_a5.run(tmp_path, {}, None)
    assert findings, "A5 must always emit at least one Finding"
    for f in findings:
        assert f.source == SOURCE_DETECTIVE_ONLY, f"check {f.check_id}"
        assert f.group == "A", f"check {f.check_id} has wrong group {f.group}"
        # IDs must be A5.X form so audit-report.md sorts them next to Group A.
        assert f.check_id.startswith("A5."), f.check_id


def test_a5_failed_findings_carry_suggested_iterate_cmd(tmp_path):
    bad = _canonical_workflow().replace(
        "        id: shipwright-critical-gate\n", "",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_4 = next(f for f in findings if f.check_id == "A5.4")
    assert a5_4.status == "fail"
    assert a5_4.suggested_iterate_cmd is not None
    assert "/shipwright-iterate" in a5_4.suggested_iterate_cmd


# ---------------------------------------------------------------------------
# A5.9 — crash isolation
# ---------------------------------------------------------------------------


def test_a5_9_crash_in_one_check_does_not_suppress_others(tmp_path, monkeypatch):
    _write_workflow(tmp_path, _canonical_workflow())

    def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic")

    # Pick a sub-check that won't short-circuit other checks.
    monkeypatch.setattr(group_a5, "_check_a5_4_critical_gate", boom)
    findings = group_a5.run(tmp_path, {}, None)
    by_id = {f.check_id: f for f in findings}
    assert "A5.4" in by_id
    assert by_id["A5.4"].status == "fail"
    assert "synthetic" in by_id["A5.4"].detail or \
           "RuntimeError" in by_id["A5.4"].detail
    # Other checks still ran:
    for cid in ("A5.3", "A5.5", "A5.6", "A5.7"):
        assert cid in by_id, f"{cid} missing — crash isolation broken"
        assert by_id[cid].status in {"pass", "fail", "skip"}


def test_a5_setup_failure_emits_single_finding(tmp_path, monkeypatch):
    """Reviewer-flagged: shared-lib loading or constants access can fail
    BEFORE individual sub-checks run. That must produce one controlled
    Finding, not crash the whole audit."""
    _write_workflow(tmp_path, _canonical_workflow())

    def boom_load(*_a, **_kw):
        raise ImportError("synthetic shared-lib failure")

    monkeypatch.setattr(group_a5, "_load_convention", boom_load)
    findings = group_a5.run(tmp_path, {}, None)
    # Exactly one setup-failure Finding.
    assert len(findings) == 1
    f = findings[0]
    assert f.status == "fail"
    assert f.severity == "HIGH"
    assert f.check_id == "A5.0"
    assert "synthetic" in f.detail or "shared-lib" in f.detail.lower() or \
           "convention" in f.detail.lower()


# ---------------------------------------------------------------------------
# Integration with audit_detector + registry composite handler
# ---------------------------------------------------------------------------


def test_register_all_keeps_group_a_and_a5_findings_visible(tmp_path):
    """The OpenAI reviewer flagged this: registering A5 on letter ``"A"``
    naively would overwrite the existing A2/A3/A4 handler. The composite
    handler must merge findings from group_a and group_a5."""
    from scripts.audit import audit_detector
    from scripts.audit._registry import register_all

    register_all()
    a_handler = audit_detector.registered_groups()["A"]

    # No CLAUDE.md / pyproject / config jsons, no workflow → A2/A3/A4 skip
    # and A5.1 skips. We assert all four IDs appear, not just A5.
    findings = a_handler(tmp_path, {}, None)
    by_id = {f.check_id: f for f in findings}
    for required in ("A2", "A3", "A4", "A5.1"):
        assert required in by_id, (
            f"expected {required} in registry-merged Group A output; "
            f"got {sorted(by_id)}"
        )


# ---------------------------------------------------------------------------
# Real-template happy-path (contract test — depends on monorepo layout)
# ---------------------------------------------------------------------------


def test_a5_passes_against_shipped_template(tmp_path):
    """Drop the real ``security.yml.template`` into tmp_path and run A5
    against it. Pins the template ↔ A5 contract in lockstep with the SSoT
    drift test (shared/tests/test_security_workflow_convention.py)."""
    repo_root = PLUGIN_ROOT.parent.parent
    template = repo_root / "shared" / "templates" / "github-actions" / "security.yml.template"
    if not template.is_file():
        pytest.skip(f"template not found at {template}")

    _write_workflow(tmp_path, template.read_text(encoding="utf-8"))
    findings = group_a5.run(tmp_path, {}, None)
    fails = [f for f in findings if f.status == "fail"]
    assert not fails, "\n".join(
        f"{f.check_id}: {f.detail}" for f in fails
    )


# ---------------------------------------------------------------------------
# Config-override safety (reviewer-flagged: bad type → fall back to default)
# ---------------------------------------------------------------------------


def test_a5_invalid_required_permissions_override_falls_back_to_default(tmp_path):
    """If ``a5_required_permissions`` is supplied as a non-dict, fall back
    to the convention-lock default rather than crashing the audit."""
    _write_workflow(tmp_path, _canonical_workflow())
    findings = group_a5.run(
        tmp_path,
        {"a5_required_permissions": ["security-events", "contents", "actions"]},
        None,
    )
    by_id = {f.check_id: f for f in findings}
    assert "A5.3" in by_id
    # Should pass (convention-lock default still satisfied by the canonical
    # workflow), NOT crash with a setup-failure.
    assert by_id["A5.3"].status == "pass", by_id["A5.3"].detail


# ---------------------------------------------------------------------------
# Post-review regression tests (code-review pass 2026-05-01)
# ---------------------------------------------------------------------------


def test_a5_7_fails_on_tautological_bypass(tmp_path):
    """Reviewer-flagged bypass: ``always() || (... full_name == ...)``
    short-circuits to True for every event — the SARIF upload would fire
    on fork PRs and break with read-only GITHUB_TOKEN. The substring
    `head.repo.full_name == github.repository` IS present, but the guard
    is functionally absent. A5.7 must require the canonical pair (both
    `event_name != 'pull_request'` AND `head.repo.full_name == github.repository`)
    so this expression fails."""
    bad = _canonical_workflow().replace(
        "        if: always() && (github.event_name != 'pull_request' "
        "|| github.event.pull_request.head.repo.full_name == github.repository)\n",
        "        if: always() || "
        "(github.event.pull_request.head.repo.full_name == github.repository)\n",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_7 = next(f for f in findings if f.check_id == "A5.7")
    assert a5_7.status == "fail"
    assert "event_name != 'pull_request'" in a5_7.detail


def test_a5_5_action_prefix_does_not_match_unrelated_action(tmp_path):
    """Reviewer-flagged false positive: ``startswith("github/codeql-action/upload-sarif")``
    would match a hypothetical ``upload-sarif-fork@v1`` action. The exact-match
    OR ``prefix + "@"`` rule rejects this."""
    bad = _canonical_workflow().replace(
        "uses: github/codeql-action/upload-sarif@v3",
        "uses: github/codeql-action/upload-sarif-fork@v1",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_5 = next(f for f in findings if f.check_id == "A5.5")
    assert a5_5.status == "fail"
    # Detail should call out missing canonical action, not category mismatch.
    assert "SARIF upload absent" in a5_5.detail or \
           "no step uses" in a5_5.detail


def test_a5_5_fails_distinctly_when_with_block_missing(tmp_path):
    """Reviewer-flagged: when `with:` is absent entirely, the old code path
    reported `"got None, expected ..."` instead of pointing at the missing
    block. The corrected check distinguishes these cases."""
    bad = _canonical_workflow().replace(
        "        with:\n          sarif_file: sarif\n          category: shipwright-security\n",
        "",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    a5_5 = next(f for f in findings if f.check_id == "A5.5")
    assert a5_5.status == "fail"
    assert "with:" in a5_5.detail
    assert "missing" in a5_5.detail.lower() or \
           "is not a mapping" in a5_5.detail


def test_a5_does_not_crash_on_jobs_null(tmp_path):
    """`jobs:` parsed as None is a legal but-broken workflow shape.
    A5.4 (gate id) and A5.5 (SARIF upload step) must surface as failures
    cleanly, not crash the run."""
    bad = _canonical_workflow().replace(
        "jobs:\n"
        "  scan:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - name: Upload SARIF\n"
        "        if: always() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)\n"
        "        uses: github/codeql-action/upload-sarif@v3\n"
        "        with:\n"
        "          sarif_file: sarif\n"
        "          category: shipwright-security\n"
        "      - name: Check for critical findings\n"
        "        id: shipwright-critical-gate\n"
        "        shell: bash\n"
        "        run: echo ok\n",
        "jobs:\n",
    )
    _write_workflow(tmp_path, bad)
    findings = group_a5.run(tmp_path, {}, None)
    by_id = {f.check_id: f for f in findings}
    # Setup + parse succeeded, A5.4 and A5.5 fail cleanly with descriptive
    # detail (not crash-finding text).
    assert "A5.4" in by_id
    assert by_id["A5.4"].status == "fail"
    assert "raised" not in by_id["A5.4"].detail  # no crash leak
    assert "A5.5" in by_id
    assert by_id["A5.5"].status == "fail"
    assert "raised" not in by_id["A5.5"].detail


def test_a5_pyyaml_missing_emits_setup_failure(tmp_path, monkeypatch):
    """Reviewer-flagged: the PyYAML import lives inside ``run()``. If the
    import fails (e.g. plugin install drift), A5 must surface a single
    A5.0 setup-failure Finding rather than crashing or returning empty."""
    _write_workflow(tmp_path, _canonical_workflow())

    import builtins
    real_import = builtins.__import__

    def deny_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("synthetic: PyYAML unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_yaml)
    # Bypass any cached `yaml` already loaded in this test session.
    monkeypatch.delitem(sys.modules, "yaml", raising=False)

    findings = group_a5.run(tmp_path, {}, None)
    assert len(findings) == 1
    f = findings[0]
    assert f.check_id == "A5.0"
    assert f.status == "fail"
    assert f.severity == "HIGH"
    assert "PyYAML" in f.detail or "yaml" in f.detail.lower()
