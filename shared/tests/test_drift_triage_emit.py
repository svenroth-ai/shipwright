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
import os
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
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")  # F7: marker req'd
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
    # Bug 1: the content dedup key path is canonicalized (drive-letter casing
    # must not split one logical drift across two items).
    assert item["dedupKey"] == f"drift:{check_drift._canonical_anchor('CLAUDE.md', project)}:content"


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
        f"drift:{check_drift._canonical_anchor('CLAUDE.md', project)}:content",
        f"drift:{check_drift._canonical_anchor('webui/CLAUDE.md', project)}:content",
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


# --- Bug 1: drive-letter casing canonicalization -------------------------

def _two_casings(tmp_path: Path) -> tuple[str, str]:
    """Two textually-distinct spellings of the same CLAUDE.md path.

    Windows: the drive letter (`c:\\…` vs `C:\\…`) — os.path.abspath does
    NOT canonicalize this. POSIX: a redundant `..` segment that
    os.path.realpath collapses (there is no drive letter to case).
    """
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("# x\n", encoding="utf-8")
    p = str(claude)
    if os.name == "nt":
        return p[0].lower() + p[1:], p[0].upper() + p[1:]
    return p, os.path.join(str(tmp_path), "sub", os.pardir, "CLAUDE.md")


def test_check_drift_drive_letter_casing_dedups_to_one_item(
    project: Path, tmp_path: Path,
) -> None:
    """Bug 1 regression: the SAME CLAUDE.md referenced with two abspath
    casings collapses to exactly ONE idempotent triage item."""
    variant_a, variant_b = _two_casings(tmp_path)
    # Distinct on the wire, identical after canonicalization.
    assert variant_a != variant_b
    assert (
        check_drift._canonical_anchor(variant_a, project)
        == check_drift._canonical_anchor(variant_b, project)
    )
    appended = check_drift._emit_drift_to_triage(
        project,
        timestamp_drifted=[],
        content_findings=[
            f"{variant_a}: Structure lists 'docs/' but directory not found",
            f"{variant_b}: Structure lists 'docs/' but directory not found",
        ],
    )
    assert appended == 1
    assert len(read_all_items(project)) == 1


def test_check_drift_drive_letter_casing_dedups_across_sessions(
    project: Path, tmp_path: Path,
) -> None:
    """Bug 1 regression, cross-session form: two SEPARATE runs that see
    the same file under different abspath casing still yield ONE item."""
    variant_a, variant_b = _two_casings(tmp_path)
    check_drift._emit_drift_to_triage(
        project, timestamp_drifted=[],
        content_findings=[
            f"{variant_a}: Structure lists 'docs/' but directory not found",
        ],
    )
    appended2 = check_drift._emit_drift_to_triage(
        project, timestamp_drifted=[],
        content_findings=[
            f"{variant_b}: Structure lists 'docs/' but directory not found",
        ],
    )
    assert appended2 == 0
    assert len(read_all_items(project)) == 1


def test_check_drift_legacy_noncanonical_item_resolved_on_recanon(
    project: Path, tmp_path: Path,
) -> None:
    """Boundary probe — legacy-key migration.

    A triage item written BEFORE the Bug 1 fix carries a non-canonical
    dedup key (raw abspath). When the same drift is re-detected after the
    fix, the producer emits the CANONICAL key and the resolve pass
    dismisses the stale legacy item — so pre-existing real duplicates
    collapse to one open item without retroactive merging.
    """
    from triage import append_triage_item_idempotent

    variant_a, variant_b = _two_casings(tmp_path)
    # Legacy item: emitted by the OLD producer with a raw, non-canonical key.
    legacy_id = append_triage_item_idempotent(
        project, source="drift", severity="medium", kind="maintenance",
        title="legacy drift", detail="d",
        dedup_key=f"drift:{variant_b}:content",
        match_commit=False, window_seconds=None,
    )
    assert legacy_id is not None

    # Post-fix run: same logical file → canonical key, distinct from legacy.
    check_drift._emit_drift_to_triage(
        project, timestamp_drifted=[],
        content_findings=[
            f"{variant_a}: Structure lists 'docs/' but directory not found",
        ],
    )
    by_id = {it["id"]: it for it in read_all_items(project)}
    # Legacy item retracted; exactly one open canonical item remains.
    assert by_id[legacy_id]["status"] == "dismissed"
    assert by_id[legacy_id]["statusReason"] == "driftResolved"
    open_items = [it for it in by_id.values() if it["status"] == "triage"]
    assert len(open_items) == 1
    assert open_items[0]["dedupKey"] == (
        f"drift:{check_drift._canonical_anchor(variant_a, project)}:content"
    )


# --- Bug 2: resolve pass auto-dismisses cleared findings -----------------

def test_check_drift_resolves_cleared_finding(project: Path) -> None:
    """Once every drift condition clears, the next run flips the still-open
    triage items to dismissed with reason=driftResolved."""
    check_drift._emit_drift_to_triage(
        project,
        timestamp_drifted=["pyproject.toml"],
        content_findings=[
            "CLAUDE.md: 'docs/' exists on disk but not listed in Structure",
        ],
    )
    items = read_all_items(project)
    assert len(items) == 2
    assert {it["status"] for it in items} == {"triage"}

    # Next run: no findings at all — both drift conditions cleared.
    check_drift._emit_drift_to_triage(
        project, timestamp_drifted=[], content_findings=[],
    )
    items = read_all_items(project)
    assert len(items) == 2  # no new items appended
    for it in items:
        assert it["status"] == "dismissed"
        assert it["statusReason"] == "driftResolved"
        assert it["statusBy"] == "driftDetector"


def test_check_drift_resolves_only_vanished_findings(project: Path) -> None:
    """A finding still present on the next run stays in triage; only the
    finding that vanished is dismissed."""
    check_drift._emit_drift_to_triage(
        project,
        timestamp_drifted=["pyproject.toml", "package.json"],
        content_findings=[],
    )
    assert len(read_all_items(project)) == 2

    # Re-run: package.json drift cleared, pyproject.toml drift persists.
    check_drift._emit_drift_to_triage(
        project, timestamp_drifted=["pyproject.toml"], content_findings=[],
    )
    by_key = {it["dedupKey"]: it for it in read_all_items(project)}
    assert by_key["drift:pyproject.toml:timestamp"]["status"] == "triage"
    assert by_key["drift:package.json:timestamp"]["status"] == "dismissed"
    assert (
        by_key["drift:package.json:timestamp"]["statusReason"]
        == "driftResolved"
    )


def test_check_drift_resolve_ignores_artifact_sync_items(project: Path) -> None:
    """check_drift's resolve pass must NOT dismiss artifact_sync.py items —
    both producers use source='drift', but artifact_sync owns the
    `:artifact` keys and runs its own emission."""
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
    # check_drift runs with NO findings — its resolve pass sees the
    # artifact item but must leave it alone (wrong key suffix).
    check_drift._emit_drift_to_triage(
        project, timestamp_drifted=[], content_findings=[],
    )
    [item] = read_all_items(project)
    assert item["dedupKey"].endswith(":artifact")
    assert item["status"] == "triage"


def test_check_drift_resolve_leaves_terminal_items(project: Path) -> None:
    """An operator-promoted drift item stays terminal even when its finding
    vanishes — the resolve pass only touches status=='triage' items."""
    from triage import mark_status

    check_drift._emit_drift_to_triage(
        project, timestamp_drifted=["pyproject.toml"], content_findings=[],
    )
    [item] = read_all_items(project)
    mark_status(project, item["id"], new_status="promoted", by="operator",
                promoted_task_id="EXT:1")

    # Finding vanishes on the next run.
    check_drift._emit_drift_to_triage(
        project, timestamp_drifted=[], content_findings=[],
    )
    [item] = read_all_items(project)
    assert item["status"] == "promoted"  # NOT flipped to dismissed


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
