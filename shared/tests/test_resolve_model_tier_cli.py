"""Smoke tests for the resolve_model_tier.py CLI wrapper.

Logic is unit-tested in test_model_tier_config.py; this only checks the CLI's
own contract (JSON shape, exit code, single-call-resolves-all-four-roles).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_TOOLS_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "tools"
_SCRIPT = _TOOLS_ROOT / "resolve_model_tier.py"


def _run(project_root: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--project-root", str(project_root), *extra_args],
        capture_output=True, text=True, check=False,
    )


def test_default_run_resolves_all_four_roles_to_inherit(tmp_path: Path) -> None:
    proc = _run(tmp_path)
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert set(payload) == {"review", "finalization", "execution", "plan_review"}
    for role in payload:
        assert payload[role] == {"resolved": "inherit", "source": "unset", "agent_param": None}


def test_flags_resolve_independently_per_role(tmp_path: Path) -> None:
    proc = _run(tmp_path, "--review-model", "opus", "--execution-model", "sonnet",
                "--plan-review-model", "haiku")
    payload = json.loads(proc.stdout)
    assert payload["review"] == {"resolved": "opus", "source": "flag", "agent_param": "opus"}
    assert payload["execution"] == {"resolved": "sonnet", "source": "flag", "agent_param": "sonnet"}
    assert payload["plan_review"] == {"resolved": "haiku", "source": "flag", "agent_param": "haiku"}
    assert payload["finalization"]["resolved"] == "inherit"


def test_invalid_plan_review_flag_warns_with_correct_flag_name(tmp_path: Path) -> None:
    """The warning must name the real CLI flag (--plan-review-model, hyphens)
    not the role's own underscore spelling (--plan_review-model)."""
    proc = _run(tmp_path, "--plan-review-model", "gpt5")
    assert "--plan-review-model" in proc.stderr
    assert "--plan_review-model" not in proc.stderr
