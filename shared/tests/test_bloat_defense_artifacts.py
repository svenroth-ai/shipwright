"""Static checks for the A.defense artifacts: the bloat-check workflow,
the bloat-exception ADR template, the glossary, and the install-hook
scripts. Covers acceptance criteria AC-4, AC-5, AC-6 structural shape
and the External-Review F8 (source-hash) + F12 (PR-comment shape).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------
# Workflow YAML
# ---------------------------------------------------------------------

_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "bloat-check.yml"


def test_workflow_exists():
    assert _WORKFLOW.is_file()


def test_workflow_triggers_on_pull_request_not_target():
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML maps the YAML key ``on:`` to Python literal True.
    triggers = doc.get(True) or doc.get("on")
    assert triggers is not None, "workflow must have an 'on:' section"
    assert "pull_request" in triggers
    assert "pull_request_target" not in triggers, (
        "fork-safety: pull_request_target is forbidden — runs untrusted "
        "PR code with elevated privileges"
    )


def test_workflow_permissions_minimal():
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    perms = doc.get("permissions") or {}
    assert perms.get("contents") == "read"
    assert perms.get("pull-requests") == "write"


def test_workflow_checkout_full_depth():
    raw = _WORKFLOW.read_text(encoding="utf-8")
    # fetch-depth: 0 is required for the base-ref diff to work.
    assert re.search(r"fetch-depth:\s*0", raw), (
        "actions/checkout MUST set fetch-depth: 0 so the base ref is "
        "resolvable for the allowlist diff"
    )


def test_workflow_uses_pr_comment_marker():
    raw = _WORKFLOW.read_text(encoding="utf-8")
    assert "<!-- shipwright-bloat-check -->" in raw, (
        "PR comment MUST use a marker for find-and-update idempotence"
    )


def test_workflow_blocks_on_anti_ratchet_only():
    raw = _WORKFLOW.read_text(encoding="utf-8")
    # The fail-step is gated by the script's exit code, not by every
    # baseline diff line.
    assert "Fail on anti-ratchet" in raw
    assert "steps.ratchet.outputs.exit_code" in raw


# ---------------------------------------------------------------------
# ADR template
# ---------------------------------------------------------------------

_ADR_TEMPLATE = (
    _REPO_ROOT / ".shipwright" / "planning" / "adr"
    / "_template-bloat-exception.md"
)


def test_adr_template_exists():
    assert _ADR_TEMPLATE.is_file()


@pytest.mark.parametrize("heading", [
    "Ousterhout Argument",
    "YAGNI Check",
    "Chesterton-Fence Check",
    "Re-Review-Date",
    "Incident Reference",
])
def test_adr_template_has_mandatory_field(heading):
    body = _ADR_TEMPLATE.read_text(encoding="utf-8")
    assert heading in body, f"missing field: {heading}"


def test_adr_template_lists_external_attribution():
    body = _ADR_TEMPLATE.read_text(encoding="utf-8")
    # All three upstream MIT projects must be acknowledged.
    assert "obra/superpowers" in body
    assert "addyosmani/agent-skills" in body
    # Multica is referenced as a pattern source, not a quoted source.
    assert "multica" in body.lower()
    assert "MIT" in body


# ---------------------------------------------------------------------
# Glossary
# ---------------------------------------------------------------------

_GLOSSARY = _REPO_ROOT / "shared" / "glossary.md"

_MANDATORY_TERMS = [
    "Allowlist",
    "Ratchet",
    "Anti-Ratchet",
    "Producer",
    "Action-Unit",
    "Canon-Gate",
]


def test_glossary_exists():
    assert _GLOSSARY.is_file()


def test_glossary_under_loc_limit():
    body = _GLOSSARY.read_text(encoding="utf-8")
    assert len(body.splitlines()) <= 300, (
        "Glossary must stay ≤300 LOC per Campaign A.defense acceptance"
    )


@pytest.mark.parametrize("term", _MANDATORY_TERMS)
def test_glossary_lists_mandatory_term(term):
    body = _GLOSSARY.read_text(encoding="utf-8")
    # Bullet entries: ``- **Allowlist** — …``
    assert re.search(rf"-\s*\*\*{re.escape(term)}\*\*", body), (
        f"glossary must define `{term}` as a top-level bullet"
    )


def test_glossary_has_at_least_30_terms():
    body = _GLOSSARY.read_text(encoding="utf-8")
    matches = re.findall(r"-\s*\*\*([^*]+)\*\*\s*—", body)
    unique = set(matches)
    assert len(unique) >= 30, (
        f"glossary must list ≥30 terms; found {len(unique)}: "
        f"{sorted(unique)}"
    )


def test_glossary_has_external_references_block():
    body = _GLOSSARY.read_text(encoding="utf-8")
    assert "## External References" in body
    # Each of the three required upstream sources must be cited with
    # both repo link + MIT attribution.
    assert "Karpathy" in body
    assert "multica-ai/andrej-karpathy-skills" in body
    assert "Osmani" in body
    assert "addyosmani/agent-skills" in body
    assert "Superpowers" in body
    assert "obra/superpowers" in body
    # Snapshot-date convention from A.review.
    assert "Snapshot date:" in body


# ---------------------------------------------------------------------
# Install-hook script idempotence (POSIX side)
# ---------------------------------------------------------------------

_INSTALL_SH = _REPO_ROOT / "scripts" / "install-hooks.sh"


def _has_bash() -> bool:
    return subprocess.run(
        ["bash", "--version"], capture_output=True
    ).returncode == 0


def test_install_hooks_idempotent(tmp_path):
    if not _has_bash():
        pytest.skip("bash not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=str(repo), check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=str(repo), check=True,
    )
    # Vendor the install script into the temp repo (relative path matters).
    target_dir = repo / "scripts" / "hooks"
    target_dir.mkdir(parents=True)
    (target_dir / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (repo / "scripts" / "install-hooks.sh").write_text(
        _INSTALL_SH.read_text(encoding="utf-8"), encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # First run installs.
    res1 = subprocess.run(
        ["bash", "scripts/install-hooks.sh"], cwd=str(repo), capture_output=True, text=True, env=env,
    )
    assert res1.returncode == 0, res1.stderr
    out = subprocess.run(
        ["git", "config", "--local", "core.hooksPath"],
        cwd=str(repo), capture_output=True, text=True,
    ).stdout.strip()
    assert out == "scripts/hooks"

    # Second run is a no-op.
    res2 = subprocess.run(
        ["bash", "scripts/install-hooks.sh"], cwd=str(repo), capture_output=True, text=True, env=env,
    )
    assert res2.returncode == 0
    assert "already set" in res2.stdout.lower()


def test_install_hooks_refuses_to_overwrite(tmp_path):
    if not _has_bash():
        pytest.skip("bash not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "config", "core.hooksPath", "custom/path"],
        cwd=str(repo), check=True,
    )
    target_dir = repo / "scripts" / "hooks"
    target_dir.mkdir(parents=True)
    (repo / "scripts" / "install-hooks.sh").write_text(
        _INSTALL_SH.read_text(encoding="utf-8"), encoding="utf-8",
    )

    res = subprocess.run(
        ["bash", "scripts/install-hooks.sh"],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert res.returncode == 1
    assert "refused" in res.stderr.lower()
