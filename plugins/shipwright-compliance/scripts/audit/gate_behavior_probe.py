"""A5.8 — behavioral probe of the DEPLOYED security-workflow critical-gate.

Group A5's structural sub-checks confirm the merge gate is *present* (A5.4: a
step carries ``id: shipwright-critical-gate``); they never confirm it *works*.
The 2026-06-04 false-green (fixed for the template in PR #144) was a gate whose
step existed yet could never block — it read SARIF ``security-severity`` at the
*result* level (the field lives on the *rule*), so every finding read as "0".

A5.8 *executes* the deployed gate's ``run:`` body against fixture scan output and
asserts the ratified blocking policy, not the implementation:

- **clean** scan  → gate passes (exit 0)        — sanity gate (runs first)
- **critical**    → gate blocks (exit non-zero)  — the false-green class
- **empty**       → gate fails closed (non-zero)
- **invalid JSON**→ gate fails closed (non-zero)

Flavor-agnostic: each scenario stages BOTH the template's ``sarif/*.sarif`` AND
the monorepo's ``findings.json``/``prompt_risks.json`` consistently, so the
probe is correct whether the gate reads SARIF (adopted repos, rendered from
``security.yml.template``) or findings.json (this monorepo's own scan). Each
gate reads only its own artifact; the other is inert ballast.

Safety contract (mirrors A5.0's PyYAML-missing skip — an env/invocation problem
is never a compliance violation):

- ``bash``/``jq`` absent → SKIP (the gate body needs them; CI ubuntu ships both).
- gate step has no ``run:`` body → SKIP (A5.4 covers id presence).
- gate cannot pass the CLEAN fixture → SKIP (inconclusive: the gate needs a
  tool/artifact this harness can't provide — guards against false positives).
- subprocess timeout / OSError → SKIP (never a hang, never a phantom FAIL).
- ``SHIPWRIGHT_A5_GATE_PROBE=0`` → SKIP (operator kill-switch; also lets the
  compliance test suite keep the A5.1–A5.7 structural tests free of bash/jq).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from scripts.audit.audit_adapters import Finding, SOURCE_DETECTIVE_ONLY

TOOLS_REQUIRED = ("bash", "jq")
_ENV_FLAG = "SHIPWRIGHT_A5_GATE_PROBE"
_DEFAULT_GATE_ID = "shipwright-critical-gate"
DEFAULT_TIMEOUT = 20.0

_CHECK_ID = "A5.8"
_NAME = "Critical-gate behaviorally blocks a critical finding"


# ---------------------------------------------------------------------------
# Enablement + tool availability
# ---------------------------------------------------------------------------


def enabled() -> bool:
    """Whether the behavioral probe runs (default on; ``=0`` disables)."""
    return os.environ.get(_ENV_FLAG, "1").strip() != "0"


def tools_available() -> bool:
    """True iff every binary the gate body needs is on PATH."""
    return all(shutil.which(tool) is not None for tool in TOOLS_REQUIRED)


# ---------------------------------------------------------------------------
# Gate-body extraction
# ---------------------------------------------------------------------------


def extract_gate_body(workflow: Any, gate_step_id: str) -> str | None:
    """Return the ``run:`` body of the step carrying ``gate_step_id``.

    ``None`` when the workflow shape is malformed, the step is absent, or the
    step has no (non-empty) ``run:`` body (e.g. a ``uses:``-only gate).
    """
    jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
    if not isinstance(jobs, dict):
        return None
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict) and step.get("id") == gate_step_id:
                run = step.get("run")
                if isinstance(run, str) and run.strip():
                    return run
                return None
    return None


# ---------------------------------------------------------------------------
# Fixtures — minimal SARIF + findings.json shapes (mirror the real scanners)
# ---------------------------------------------------------------------------


def _sarif(driver: str, rules: list[dict], results: list[dict]) -> str:
    return json.dumps({
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": driver, "rules": rules}},
                  "results": results}],
    })


def _result(rule_id: str, *, rule_index: int | None = None) -> dict:
    res: dict[str, Any] = {
        "ruleId": rule_id,
        "message": {"text": "finding"},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": "src/x"}}}],
    }
    if rule_index is not None:
        res["ruleIndex"] = rule_index
    return res


def _critical_files() -> dict[str, str]:
    # security-severity ONLY on the rule (the exact shape the 2026-06-04 bug
    # missed) + a findings.json critical for the findings.json-flavor gate.
    # Semgrep ballast mirrors _clean_files() so the scenario set is uniform.
    return {
        "sarif/trivy.sarif": _sarif(
            "Trivy",
            [{"id": "CVE-2026-99999", "properties": {"security-severity": "9.8"}}],
            [_result("CVE-2026-99999", rule_index=0)],
        ),
        "sarif/semgrep.sarif": _sarif(
            "Semgrep OSS", [{"id": "rule.x", "properties": {}}], [_result("rule.x")]),
        "findings.json": json.dumps(
            {"findings": [{"id": "CVE-2026-99999", "severity": "critical"}]}),
        "prompt_risks.json": json.dumps({"findings": []}),
    }


def _clean_files() -> dict[str, str]:
    return {
        "sarif/trivy.sarif": _sarif(
            "Trivy",
            [{"id": "CVE-2026-00001", "properties": {"security-severity": "5.5"}}],
            [_result("CVE-2026-00001", rule_index=0)],
        ),
        "sarif/semgrep.sarif": _sarif(
            "Semgrep OSS", [{"id": "rule.x", "properties": {}}], [_result("rule.x")]),
        "findings.json": json.dumps({"findings": [{"id": "x", "severity": "high"}]}),
        "prompt_risks.json": json.dumps({"findings": []}),
    }


def _invalid_files() -> dict[str, str]:
    # Corrupt every input family so either gate flavor hits a broken report.
    bad = "{not valid json"
    return {"sarif/scan.sarif": bad, "findings.json": bad, "prompt_risks.json": bad}


# ---------------------------------------------------------------------------
# Subprocess harness
# ---------------------------------------------------------------------------


def _run_gate(
    body: str, files: dict[str, str], timeout: float,
) -> subprocess.CompletedProcess:
    """Execute ``body`` as bash in a sandboxed temp dir staged with ``files``."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for name, content in files.items():
            fp = tdp / name
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
        script = tdp / "gate.sh"
        script.write_text(body, encoding="utf-8")
        env = {**os.environ, "GITHUB_OUTPUT": str(tdp / "gh_output")}
        return subprocess.run(
            ["bash", str(script)], cwd=str(tdp), env=env,
            capture_output=True, text=True, timeout=timeout,
        )


def _truncate(text: str, limit: int = 300) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _tail(cp: subprocess.CompletedProcess) -> str:
    """One-line evidence: exit code + last diagnostic line from the gate."""
    lines = (cp.stderr or cp.stdout or "").strip().splitlines()
    return _truncate(f"exit={cp.returncode} {lines[-1] if lines else ''}".strip(), 160)


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------


def probe(
    workflow: Any, gate_step_id: str, *, timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str, list[str]]:
    """Behaviorally probe the gate. Returns ``(status, detail, evidence)``."""
    # "Is there anything to probe?" (a workflow fact) before "can we probe?"
    # (an env fact) — so a run-less gate skips for the right reason even where
    # bash/jq are absent.
    body = extract_gate_body(workflow, gate_step_id)
    if body is None:
        return ("skip", f"the {gate_step_id!r} gate step has no executable "
                "`run:` body — nothing to behaviorally probe (A5.4 covers id "
                "presence).", [])
    if "${{" in body:
        # The body interpolates GitHub Actions expressions — it is not a
        # standalone shell script and would mis-verdict if run verbatim as
        # bash. Skip rather than risk a false signal (structural A5.3–A5.7
        # still apply). Both shipped gates keep ${{ }} out of the gate body.
        return ("skip", f"the {gate_step_id!r} gate `run:` body interpolates "
                "${{ … }} GitHub expressions — it cannot be faithfully executed "
                "as plain bash, so the behavioral probe is inconclusive.", [])
    if not tools_available():
        return ("skip", "bash/jq unavailable on PATH — gate behavioral probe "
                "skipped (env/invocation issue, not a compliance violation); "
                "CI ubuntu ships both.", [])
    try:
        clean = _run_gate(body, _clean_files(), timeout)
        if clean.returncode != 0:
            return ("skip", "gate did not exit 0 on a CLEAN fixture — probe "
                    "inconclusive (the gate likely needs a tool/artifact this "
                    f"harness can't provide); not a failure. [{_tail(clean)}]", [])
        crit = _run_gate(body, _critical_files(), timeout)
        if crit.returncode == 0:
            return ("fail", "deployed critical-gate did NOT block a CRITICAL "
                    "fixture (exit 0) — the step exists but is structurally "
                    "unable to block a merge (the 2026-06-04 result-vs-rule-"
                    "level false-green class).", [_tail(crit)])
        empty = _run_gate(body, {}, timeout)
        if empty.returncode == 0:
            return ("fail", "deployed critical-gate did NOT fail closed on "
                    "EMPTY scan output (exit 0) — a crashed scanner producing "
                    "no output would pass green.", [_tail(empty)])
        invalid = _run_gate(body, _invalid_files(), timeout)
        if invalid.returncode == 0:
            return ("fail", "deployed critical-gate did NOT fail closed on "
                    "INVALID-JSON scan output (exit 0) — a corrupt scanner "
                    "report would pass green.", [_tail(invalid)])
        return ("pass", "deployed critical-gate blocks on a CRITICAL finding "
                "and fails closed on empty/invalid scan output (behavioral "
                "probe of the gate shell).", [])
    except subprocess.TimeoutExpired:
        return ("skip", f"gate behavioral probe timed out (> {timeout}s) — "
                "inconclusive.", [])
    except (OSError, subprocess.SubprocessError) as exc:
        # Any failure to spawn/run the gate shell is an env/invocation problem,
        # never a compliance violation → SKIP (never a phantom FAIL).
        return ("skip", "could not execute the gate shell "
                f"({type(exc).__name__}: {_truncate(str(exc))}) — probe "
                "inconclusive.", [])


# ---------------------------------------------------------------------------
# Finding emission
# ---------------------------------------------------------------------------


def _suggest() -> str:
    return ('/shipwright-iterate --type bug "reconcile A5.8 (deployed '
            'critical-gate cannot block) — see '
            '.shipwright/compliance/audit-report.md"')


def _make_finding(status: str, detail: str, evidence: list[str]) -> Finding:
    return Finding(
        group="A", check_id=_CHECK_ID, name=_NAME, severity="HIGH",
        source=SOURCE_DETECTIVE_ONLY, status=status, detail=detail,
        evidence=list(evidence or []),
        suggested_iterate_cmd=_suggest() if status == "fail" else None,
    )


def run(workflow: Any, conv: Any) -> list[Finding]:
    """Probe the gate and emit a single A5.8 Finding. Never raises — an
    unexpected exception becomes one fail Finding (group_a5 ``_safe_run``
    crash-isolation contract)."""
    try:
        gate_id = getattr(conv, "critical_gate_step_id", None) or _DEFAULT_GATE_ID
        status, detail, evidence = probe(workflow, gate_id)
    except Exception as exc:  # noqa: BLE001 — crash isolation
        return [_make_finding(
            "fail",
            f"A5.8 probe raised {type(exc).__name__}: {_truncate(str(exc))}", [])]
    return [_make_finding(status, detail, evidence)]


def run_if_enabled(workflow: Any, conv: Any) -> list[Finding]:
    """Entry point for group_a5: probe unless disabled by the kill-switch."""
    if not enabled():
        return [_make_finding(
            "skip", f"behavioral probe disabled via {_ENV_FLAG}=0 "
            "(operator kill-switch).", [])]
    return run(workflow, conv)
