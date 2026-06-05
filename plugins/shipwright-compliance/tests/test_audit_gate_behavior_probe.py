"""Behavioral probe for the DEPLOYED security-workflow critical-gate (A5.8).

A5.4 confirms the merge gate is *present* (a step carries
``id: shipwright-critical-gate``); A5.8 confirms it *works*. The 2026-06-04
false-green read SARIF ``security-severity`` at the *result* level (it lives on
the *rule*), so a real CVSS-critical sailed through green.
``shared/tests/test_security_critical_gate.py`` pins the *template* gate; this
module pins A5.8 — the audit check that *executes* the **deployed** gate against
fixtures and asserts the ratified policy (critical → block, empty/invalid → fail
closed, clean → pass).

Flavor-agnostic: each scenario stages BOTH the template's ``sarif/*.sarif`` AND
the monorepo's ``findings.json`` consistently, so the probe is correct whether
the gate reads SARIF (adopted repos) or findings.json (this repo's own scan).

Executes the real ``bash``+``jq``; per ADR-044 CI-discipline the missing-binary
guard hard-fails in CI (ubuntu ships both) and skips locally.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

REPO_ROOT = Path(__file__).resolve().parents[3]
_SHARED_SCRIPTS = REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

# PyYAML is a compliance-plugin dep — same gate as the SSoT drift test.
yaml = pytest.importorskip("yaml")

from scripts.audit import gate_behavior_probe  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY  # noqa: E402
from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402

# Convention-lock value (pinned independently by the A5 SSoT drift test). Held
# as a literal here to avoid the `lib` namespace collision that the compliance
# audit's adapter layer guards against.
GATE_ID = "shipwright-critical-gate"
TEMPLATE_FILE = REPO_ROOT / "shared" / "templates" / "github-actions" / "security.yml.template"
DEPLOYED_FILE = REPO_ROOT / ".github" / "workflows" / "security.yml"

_CONV = types.SimpleNamespace(critical_gate_step_id=GATE_ID)


# --------------------------------------------------------------------------- #
# Synthetic gate bodies — each models one (broken or valid) gate shape
# --------------------------------------------------------------------------- #
_GATE_NOOP = "echo ok\n"  # step exists, does nothing — can never block

_GATE_OVERBLOCK = "echo blocking; exit 1\n"  # blocks every input incl. clean

# The 2026-06-04 bug: reads security-severity at the RESULT level only (never
# resolves the rule), so a rule-level critical reads as 0 — only CRITICAL exposes it.
_GATE_RESULT_LEVEL_ONLY = r"""
set -e
shopt -s nullglob
files=(sarif/*.sarif)
if [ ${#files[@]} -eq 0 ]; then echo "::error::no sarif"; exit 1; fi
critical=0
for f in "${files[@]}"; do
  if ! jq empty "$f" 2>/dev/null; then echo "::error::invalid json"; exit 1; fi
  c=$(jq '[ .runs[]? | .results[]?
            | (.properties["security-severity"] // "0")
            | (try tonumber catch 0) | select(. >= 9.0) ] | length' "$f")
  critical=$((critical + c))
done
[ "$critical" -gt 0 ] && exit 1
exit 0
"""

# Blocks a critical correctly but swallows a missing findings.json as "0"
# (the `2>/dev/null || echo 0` anti-pattern) — fails to fail closed on EMPTY.
_GATE_NOT_FAIL_CLOSED = r"""
set -e
critical=$(jq '[.findings[]? | select(.severity == "critical")] | length' findings.json 2>/dev/null || echo 0)
[ "$critical" -gt 0 ] && exit 1
exit 0
"""

# Fail-closes on EMPTY but has no `jq empty` precheck, so an INVALID findings.json
# is swallowed as "0" — passes CLEAN/CRITICAL/EMPTY, exits 0 on INVALID.
_GATE_TOLERATES_INVALID = r"""
set -e
if [ ! -f findings.json ]; then echo "::error::empty"; exit 1; fi
critical=$(jq '[.findings[]? | select(.severity == "critical")] | length' findings.json 2>/dev/null || echo 0)
[ "$critical" -gt 0 ] && exit 1
exit 0
"""


def _wf_with_gate(run_body: str | None, *, gate_id: str = GATE_ID) -> dict:
    """A minimal workflow dict carrying one gate step (optionally run-less)."""
    step: dict = {"name": "Check for critical findings", "id": gate_id, "shell": "bash"}
    if run_body is not None:
        step["run"] = run_body
    return {"jobs": {"scan": {"runs-on": "ubuntu-latest", "steps": [step]}}}


# need_tools — behavioural cases require bash+jq (CI-hard, local-skip per ADR-044)
@pytest.fixture
def need_tools() -> None:
    skip_or_fail_on_missing_binary("bash", "Git for Windows ships bash; CI ubuntu has it.")
    skip_or_fail_on_missing_binary("jq", "Install jq (winget install jqlang.jq); CI ubuntu ships it.")


# Positive controls — the REAL shipped gates must PASS (both flavors)
def test_probe_passes_against_real_template_gate(need_tools) -> None:
    assert TEMPLATE_FILE.is_file(), f"repo invariant: {TEMPLATE_FILE} missing"
    wf = yaml.safe_load(TEMPLATE_FILE.read_text(encoding="utf-8"))
    status, detail, _ = gate_behavior_probe.probe(wf, GATE_ID)
    assert status == "pass", detail


def test_probe_passes_against_real_deployed_monorepo_gate(need_tools) -> None:
    """The deployed gate reads findings.json (not SARIF). The dual-artifact
    fixtures must still classify it correctly → PASS."""
    assert DEPLOYED_FILE.is_file(), f"repo invariant: {DEPLOYED_FILE} missing"
    wf = yaml.safe_load(DEPLOYED_FILE.read_text(encoding="utf-8"))
    status, detail, _ = gate_behavior_probe.probe(wf, GATE_ID)
    assert status == "pass", detail


# Negative controls — structurally-broken gates must FAIL
def test_probe_fails_on_noop_gate(need_tools) -> None:
    """A present-but-inert ``echo ok`` gate exits 0 on a critical → FAIL."""
    status, detail, _ = gate_behavior_probe.probe(_wf_with_gate(_GATE_NOOP), GATE_ID)
    assert status == "fail", detail
    assert "CRITICAL" in detail or "block" in detail.lower()


def test_probe_fails_on_result_level_only_gate(need_tools) -> None:
    """The exact 2026-06-04 bug: result-level security-severity read never
    resolves a rule-level critical → gate exits 0 on a critical → FAIL."""
    status, detail, _ = gate_behavior_probe.probe(
        _wf_with_gate(_GATE_RESULT_LEVEL_ONLY), GATE_ID
    )
    assert status == "fail", detail


def test_probe_fails_when_gate_not_fail_closed_on_empty(need_tools) -> None:
    """A gate that blocks criticals but swallows a missing findings.json as
    "0" passes CLEAN+CRITICAL but exits 0 on EMPTY → FAIL (not fail-closed)."""
    status, detail, _ = gate_behavior_probe.probe(
        _wf_with_gate(_GATE_NOT_FAIL_CLOSED), GATE_ID
    )
    assert status == "fail", detail
    assert "EMPTY" in detail or "fail closed" in detail.lower()


def test_probe_fails_when_gate_tolerates_invalid_json(need_tools) -> None:
    """A gate that fail-closes on EMPTY but lacks a `jq empty` precheck exits 0
    on INVALID JSON → FAIL (end-to-end, real subprocess path)."""
    status, detail, _ = gate_behavior_probe.probe(
        _wf_with_gate(_GATE_TOLERATES_INVALID), GATE_ID)
    assert status == "fail", detail
    assert "INVALID" in detail


# Inconclusive / not-applicable → SKIP (never FAIL)
def test_probe_skips_on_overblocking_gate(need_tools) -> None:
    """A gate that exits non-zero even on a CLEAN scan fails the sanity gate
    → SKIP (inconclusive: probe env can't satisfy the gate's assumptions)."""
    status, detail, _ = gate_behavior_probe.probe(_wf_with_gate(_GATE_OVERBLOCK), GATE_ID)
    assert status == "skip", detail
    assert "clean" in detail.lower() or "inconclusive" in detail.lower()


def test_probe_skips_when_gate_has_no_run_body() -> None:
    """A ``uses:``-only gate step has nothing to execute → SKIP (A5.4 already
    covers id presence). No bash needed — returns before any subprocess."""
    status, detail, _ = gate_behavior_probe.probe(_wf_with_gate(None), GATE_ID)
    assert status == "skip", detail
    assert "run" in detail.lower()


def test_probe_skips_when_gate_step_absent() -> None:
    wf = _wf_with_gate(_GATE_NOOP, gate_id="some-other-id")
    status, detail, _ = gate_behavior_probe.probe(wf, GATE_ID)
    assert status == "skip", detail
    assert "run" in detail.lower()  # resolves to the "no run: body" skip


def test_probe_skips_when_tools_unavailable(monkeypatch) -> None:
    """bash/jq absent is an ENV problem, not a compliance violation → SKIP
    (mirrors the A5.0 PyYAML-missing skip). No subprocess is attempted."""
    monkeypatch.setattr(gate_behavior_probe, "tools_available", lambda: False)
    status, detail, _ = gate_behavior_probe.probe(_wf_with_gate(_GATE_NOOP), GATE_ID)
    assert status == "skip", detail
    assert "bash" in detail.lower() or "jq" in detail.lower()


def test_extract_gate_body_returns_run_string() -> None:
    body = gate_behavior_probe.extract_gate_body(_wf_with_gate("echo hi\n"), GATE_ID)
    assert body == "echo hi\n"


def test_extract_gate_body_none_when_no_run_or_malformed() -> None:
    assert gate_behavior_probe.extract_gate_body(_wf_with_gate(None), GATE_ID) is None
    assert gate_behavior_probe.extract_gate_body({"jobs": None}, GATE_ID) is None
    assert gate_behavior_probe.extract_gate_body({"jobs": [1, 2]}, GATE_ID) is None


def test_run_emits_single_a5_8_finding_with_contract(need_tools) -> None:
    findings = gate_behavior_probe.run(_wf_with_gate(_GATE_NOOP), _CONV)
    assert len(findings) == 1
    f = findings[0]
    assert f.check_id == "A5.8"
    assert f.group == "A"
    assert f.source == SOURCE_DETECTIVE_ONLY
    assert f.status == "fail"            # echo-ok gate can't block
    assert f.severity == "HIGH"
    assert f.suggested_iterate_cmd and "/shipwright-iterate" in f.suggested_iterate_cmd


def test_run_skip_finding_carries_no_suggested_cmd() -> None:
    """No-run-body gate → skip Finding, and skips never carry a remediation cmd."""
    findings = gate_behavior_probe.run(_wf_with_gate(None), _CONV)
    assert len(findings) == 1
    assert findings[0].status == "skip"
    assert findings[0].suggested_iterate_cmd is None


def test_run_never_raises_on_internal_error(monkeypatch) -> None:
    """``run`` is crash-isolated: an exception inside the probe becomes one
    A5.8 fail Finding, not a propagated exception (group_a5 ``_safe_run``
    contract)."""
    def boom(*_a, **_kw):
        raise RuntimeError("synthetic probe crash")

    monkeypatch.setattr(gate_behavior_probe, "probe", boom)
    findings = gate_behavior_probe.run(_wf_with_gate(_GATE_NOOP), _CONV)
    assert len(findings) == 1
    assert findings[0].check_id == "A5.8"
    assert findings[0].status == "fail"
    assert "synthetic" in findings[0].detail or "RuntimeError" in findings[0].detail


# run_if_enabled() — the group_a5 integration gate (env kill-switch)
def test_run_if_enabled_skips_without_probing_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SHIPWRIGHT_A5_GATE_PROBE", "0")

    def boom(*_a, **_kw):  # must NOT be reached when disabled
        raise AssertionError("probe ran while disabled")

    monkeypatch.setattr(gate_behavior_probe, "probe", boom)
    findings = gate_behavior_probe.run_if_enabled(_wf_with_gate(_GATE_NOOP), _CONV)
    assert len(findings) == 1
    assert findings[0].check_id == "A5.8"
    assert findings[0].status == "skip"
    assert "SHIPWRIGHT_A5_GATE_PROBE" in findings[0].detail


def test_run_if_enabled_probes_when_enabled(monkeypatch, need_tools) -> None:
    monkeypatch.setenv("SHIPWRIGHT_A5_GATE_PROBE", "1")
    findings = gate_behavior_probe.run_if_enabled(_wf_with_gate(_GATE_NOOP), _CONV)
    assert len(findings) == 1
    assert findings[0].status == "fail"  # echo-ok gate probed and flagged


def test_enabled_default_is_on(monkeypatch) -> None:
    monkeypatch.delenv("SHIPWRIGHT_A5_GATE_PROBE", raising=False)
    assert gate_behavior_probe.enabled() is True
    monkeypatch.setenv("SHIPWRIGHT_A5_GATE_PROBE", "0")
    assert gate_behavior_probe.enabled() is False


# Integration — A5.8 is wired into group_a5.run() output
def test_a5_8_present_in_group_a5_run_when_enabled(tmp_path, monkeypatch, need_tools) -> None:
    """End-to-end: group_a5.run() includes an A5.8 finding when the probe is
    enabled and a workflow with a (broken) gate is present."""
    monkeypatch.setenv("SHIPWRIGHT_A5_GATE_PROBE", "1")
    from scripts.audit import group_a5

    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    # A structurally-valid-but-behaviorally-inert workflow (echo-ok gate).
    (wf_dir / "security.yml").write_text(
        "on:\n  workflow_dispatch:\n"
        "permissions:\n  contents: read\n  actions: read\n  security-events: write\n"
        "jobs:\n  scan:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: github/codeql-action/upload-sarif@v4\n"
        "        if: always() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)\n"
        "        with:\n          sarif_file: sarif\n          category: shipwright-security\n"
        "      - name: Check for critical findings\n"
        "        id: shipwright-critical-gate\n        shell: bash\n        run: echo ok\n",
        encoding="utf-8",
    )
    findings = group_a5.run(tmp_path, {}, None)
    a5_8 = [f for f in findings if f.check_id == "A5.8"]
    assert len(a5_8) == 1, [f.check_id for f in findings]
    assert a5_8[0].status == "fail"  # echo-ok gate cannot block
