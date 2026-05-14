"""AC-5 producer test: Drift findings land in triage.jsonl.

Covers both emission sites in one file (per iterate-2 spec):
- `shared/scripts/hooks/check_drift.py::_emit_drift_to_triage`
- `shared/scripts/artifact_sync.py::_emit_drift_to_triage`

Both producers use the same triage schema (source="drift", severity="medium",
kind="maintenance", match_commit=False, window_seconds=None) so they share
the same dedup test surface.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_CHECK_DRIFT_PATH = _SHARED_SCRIPTS / "hooks" / "check_drift.py"
_check_drift_spec = importlib.util.spec_from_file_location(
    "check_drift_for_test", _CHECK_DRIFT_PATH,
)
assert _check_drift_spec is not None and _check_drift_spec.loader is not None
check_drift = importlib.util.module_from_spec(_check_drift_spec)
_check_drift_spec.loader.exec_module(check_drift)

_ARTIFACT_SYNC_PATH = _SHARED_SCRIPTS / "artifact_sync.py"
_as_spec = importlib.util.spec_from_file_location(
    "artifact_sync_for_test", _ARTIFACT_SYNC_PATH,
)
assert _as_spec is not None and _as_spec.loader is not None
artifact_sync = importlib.util.module_from_spec(_as_spec)
_as_spec.loader.exec_module(artifact_sync)

from triage import read_all_items  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


# --- check_drift.py producer --------------------------------------------

def test_check_drift_timestamp_only_emits_per_file(project: Path) -> None:
    """One timestamp-drift finding per file in the list."""
    appended = check_drift._emit_drift_to_triage(
        project,
        timestamp_drifted=["pyproject.toml", "package.json"],
        content_findings=[],
    )
    assert appended == 2
    items = read_all_items(project)
    keys = {it["dedupKey"] for it in items}
    assert "drift:pyproject.toml:timestamp" in keys
    assert "drift:package.json:timestamp" in keys
    for it in items:
        assert it["source"] == "drift"
        assert it["severity"] == "medium"
        assert it["kind"] == "maintenance"
        assert it["suggestedPriority"] == "P2"


def test_check_drift_content_findings_dedup_by_file(project: Path) -> None:
    """Two content findings on the SAME file collapse to one triage item
    (dedup-key is file:content; same file is the same noise source).
    """
    appended = check_drift._emit_drift_to_triage(
        project, timestamp_drifted=[],
        content_findings=[
            "CLAUDE.md: 'docs/' exists on disk but not listed in Structure",
            "CLAUDE.md: references 'npm run xx' but not defined in package.json",
        ],
    )
    assert appended == 1
    [item] = read_all_items(project)
    assert item["dedupKey"] == "drift:CLAUDE.md:content"


def test_check_drift_content_findings_per_distinct_file(project: Path) -> None:
    """Content findings on DIFFERENT files emit one item per file."""
    appended = check_drift._emit_drift_to_triage(
        project, timestamp_drifted=[],
        content_findings=[
            "CLAUDE.md: 'docs/' exists on disk but not listed in Structure",
            "webui/CLAUDE.md: 'src/' exists on disk but not listed in Structure",
        ],
    )
    assert appended == 2
    keys = {it["dedupKey"] for it in read_all_items(project)}
    assert keys == {
        "drift:CLAUDE.md:content",
        "drift:webui/CLAUDE.md:content",
    }


def test_check_drift_both_kinds_combined(project: Path) -> None:
    check_drift._emit_drift_to_triage(
        project,
        timestamp_drifted=["pyproject.toml"],
        content_findings=[
            "CLAUDE.md: 'docs/' exists on disk but not listed in Structure",
        ],
    )
    items = read_all_items(project)
    assert len(items) == 2
    kinds = {it["dedupKey"].split(":")[-1] for it in items}
    assert kinds == {"timestamp", "content"}


def test_check_drift_no_findings_no_op(project: Path) -> None:
    appended = check_drift._emit_drift_to_triage(
        project, timestamp_drifted=[], content_findings=[],
    )
    assert appended == 0
    assert read_all_items(project) == []


def test_check_drift_dedups_across_sessions(project: Path) -> None:
    """match_commit=False, window=None → same file:kind stays ONE item."""
    check_drift._emit_drift_to_triage(
        project, timestamp_drifted=["pyproject.toml"], content_findings=[],
    )
    appended2 = check_drift._emit_drift_to_triage(
        project, timestamp_drifted=["pyproject.toml"], content_findings=[],
    )
    assert appended2 == 0
    assert len(read_all_items(project)) == 1


# --- artifact_sync.py producer ------------------------------------------

def test_artifact_sync_one_item_per_affected_mapping(project: Path) -> None:
    affected = [
        {
            "pattern": "src/auth/*.ts",
            "changed_files": ["src/auth/login.ts"],
            "artifacts": [".shipwright/planning/01-auth/spec.md"],
            "frs": ["FR-01.02"],
            "category": "auth",
        },
        {
            "pattern": "src/dashboard/*.tsx",
            "changed_files": ["src/dashboard/page.tsx"],
            "artifacts": [".shipwright/planning/02-dashboard/spec.md"],
            "frs": ["FR-02.05"],
            "category": "dashboard",
        },
    ]
    appended = artifact_sync._emit_drift_to_triage(project, affected)
    assert appended == 2
    items = read_all_items(project)
    keys = {it["dedupKey"] for it in items}
    assert any("drift:" in k and ":artifact" in k for k in keys)
    for it in items:
        assert it["source"] == "drift"
        assert it["severity"] == "medium"
        assert it["kind"] == "maintenance"


def test_artifact_sync_empty_affected_no_op(project: Path) -> None:
    appended = artifact_sync._emit_drift_to_triage(project, [])
    assert appended == 0
    assert read_all_items(project) == []


def test_artifact_sync_dedups_across_sessions(project: Path) -> None:
    affected = [
        {
            "pattern": "src/auth/*.ts",
            "changed_files": ["src/auth/login.ts"],
            "artifacts": [],
            "frs": ["FR-01.02"],
            "category": "auth",
        },
    ]
    artifact_sync._emit_drift_to_triage(project, affected)
    appended2 = artifact_sync._emit_drift_to_triage(project, affected)
    assert appended2 == 0
    assert len(read_all_items(project)) == 1


# --- Cross-producer: both sources share the schema ----------------------

def test_both_sites_emit_compatible_items(project: Path) -> None:
    """A drift item from either site reads the same shape via read_all_items."""
    check_drift._emit_drift_to_triage(
        project, timestamp_drifted=["pyproject.toml"], content_findings=[],
    )
    artifact_sync._emit_drift_to_triage(
        project,
        [{
            "pattern": "src/auth/*.ts",
            "changed_files": ["src/auth/login.ts"],
            "artifacts": [],
            "frs": ["FR-01.02"],
            "category": "auth",
        }],
    )
    items = read_all_items(project)
    assert len(items) == 2
    for it in items:
        assert it["source"] == "drift"
        assert it["severity"] == "medium"
        assert it["kind"] == "maintenance"
        assert it["suggestedDomain"] == "engineering"
