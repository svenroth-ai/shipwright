"""The F11 cross-layer gate scans the folders a stack profile declares (GitHub issue #972).

The gate rebuilds the requirement-to-test index from throwaway ARCHIVES of the base and head commits,
so it only sees tracked files. A vite-hono project keeps its tests in ``server/tests`` and has no
``shipwright_compliance_config.json``: the profile named in the committed ``shipwright_run_config.json``
must be what makes the gate see them. The second test pins the stated limit: with the run config left
out of the commit the gate falls back to the default folders and reports the layer as missing, and its
failure text says why.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import evidence_drop  # noqa: E402
from tools.verifiers.layer_coverage import check_cross_layer_coverage  # noqa: E402


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git not available")

_SPEC = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-08.01 | Widget renders | Must | unit |\n"
)
_SPEC_CHANGED = _SPEC.replace("Widget renders", "Widget renders with totals")
_TEST_REL = "server/tests/test_widget.py"
_TEST = 'import pytest\n\n\n@pytest.mark.covers("FR-08.01")\ndef test_widget():\n    assert True\n'
_RUN_ID = "iterate-profile-roots"


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _commit(root: Path, msg: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)
    return _git(root, "rev-parse", "HEAD")


def _run_config(*, with_profile: bool) -> str:
    cfg = {"iterate_history": [{"run_id": _RUN_ID, "complexity": "medium", "type": "feature"}]}
    if with_profile:
        cfg["profile"] = "vite-hono"
    return json.dumps(cfg)


def _make_repo(tmp_path: Path, *, run_config_committed: bool) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.dev")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC)
    _write(root, _TEST_REL, _TEST)
    _write(root, ".gitignore", ".shipwright/compliance/\n" + ("" if run_config_committed else "shipwright_run_config.json\n"))
    if run_config_committed:
        _write(root, "shipwright_run_config.json", _run_config(with_profile=True))
    _commit(root, "base")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_CHANGED)
    head = _commit(root, "head: behaviour delta")
    # The working tree always has the run config (the gate reads the complexity from it); only
    # whether it is COMMITTED differs, which is what the archives see.
    _write(root, "shipwright_run_config.json", _run_config(with_profile=True))
    report = root / "junit.xml"
    report.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest">'
        f'<testcase classname="x" file="{_TEST_REL}" name="test_widget"></testcase></testsuite></testsuites>\n',
        encoding="utf-8")
    evidence_drop.stage_reports(root, run_id=_RUN_ID, junit=report, head_commit=head)
    return root, head


@pytest.mark.covers("FR-01.10/AC16")
def test_gate_sees_the_profile_declared_folder_from_a_committed_run_config(tmp_path):
    root, head = _make_repo(tmp_path, run_config_committed=True)
    result = check_cross_layer_coverage(root, _RUN_ID, head)
    assert result.ok is True and not result.is_skipped, result.detail
    assert "covered+passing" in result.detail


@pytest.mark.covers("FR-01.10/AC16")
def test_gate_falls_back_to_the_defaults_when_the_run_config_is_not_committed(tmp_path):
    root, head = _make_repo(tmp_path, run_config_committed=False)
    result = check_cross_layer_coverage(root, _RUN_ID, head)
    assert result.ok is False, result.detail
    assert "shipwright_run_config.json is committed" in result.detail  # the stated limit names its cause
