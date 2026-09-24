"""Tests for ``check_agents_md_completion`` (project_checks.py).

Split into its own file rather than added to ``test_verifiers_project.py``
for the same reason that file's own docstring already gives for
``test_project_gate_basis_and_guidance.py`` /
``test_project_gate_no_empty_split.py``: staying under the shared bloat
gate's 300-line limit.

This is the executable backstop the required PR-review gate asked for
twice on iterate-2026-09-23-m5-agents-md-generation-drift (R4): greenfield
AGENTS.md generation (project-scaffolding.md step 2) is agent-instruction-
driven prose, so nothing previously proved a real scaffolding run actually
produced an AGENTS.md carrying the shared Codex appendix.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.verifiers.project_checks import (  # noqa: E402
    _read_codex_appendix_marker,
    check_agents_md_completion,
)


@pytest.mark.parametrize("scope,agents_md,expect_ok,expect_in_detail", [
    ("extension", None, True, "extension"),
    (None, None, True, ""),  # no project config yet — nothing to check
    ("full_app", None, False, "missing"),
    ("full_app", "# AGENTS\n\nno appendix here.\n", False, "marker"),
])
def test_agents_md_completion(tmp_path, scope, agents_md, expect_ok, expect_in_detail):
    if scope is not None:
        (tmp_path / "shipwright_project_config.json").write_text(json.dumps({"scope": scope}))
    if agents_md is not None:
        (tmp_path / "AGENTS.md").write_text(agents_md)
    r = check_agents_md_completion(tmp_path)
    assert r.ok is expect_ok
    if expect_in_detail:
        assert expect_in_detail in r.detail.lower()


def test_agents_md_completion_passes_with_marker_present(tmp_path):
    marker = _read_codex_appendix_marker()
    assert marker, "shared/templates/codex-agents-md-appendix.md must be readable"
    (tmp_path / "shipwright_project_config.json").write_text(json.dumps({"scope": "full_app"}))
    (tmp_path / "AGENTS.md").write_text(f"# AGENTS\n\n{marker}\n## Codex operating policy\n")
    assert check_agents_md_completion(tmp_path).ok is True
