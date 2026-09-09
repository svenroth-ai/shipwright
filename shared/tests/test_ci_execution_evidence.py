"""Tests for shared/scripts/ci_execution_evidence.py —
resolve_execution_evidence() (P3.5 restart, round 2 design; round 3 fixes
after external code review flagged the artifact-selection/download split).

Composition tests: `resolve_ci_verification` is mocked directly (its own
behavior is already covered by test_ci_provenance*.py) — these tests only
prove THIS module's composition logic: what it does with each verification
outcome, the artifacts-list / download / content-binding steps, and the
three-outcome contract (confirmed / unavailable / error), never conflating
"no evidence exists yet" with "the query itself failed."
"""

from __future__ import annotations

import copy
import io
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import ci_execution_evidence as m  # noqa: E402
import github_api  # noqa: E402
from ci_provenance import CIVerification  # noqa: E402

_COMMIT = "a" * 40
_OWNER, _REPO = "acme", "foo"
_RUN_ID = 101
_ARTIFACT_ID = 555
_ARTIFACT_NAME = m.EXECUTION_EVIDENCE_ARTIFACT_NAME


def _committed_manifest(**req_overrides) -> dict:
    # Keyed the REAL, namespaced way (`NN::FR-XX.YY`) -- not the bare `id`
    # field a node carries internally. Round-3 post-push fix: an earlier
    # version of this fixture used "FR-01.01" as BOTH the dict key and the
    # node's own `id`, so it could never exercise the key/id mismatch that
    # hid a real consumer-side bug (`promote_required_layers.plan_promotions`
    # looking up by `node["id"]` against a dict actually keyed the namespaced
    # way) for three review rounds.
    reqs = {
        "01::FR-01.01": {
            "id": "FR-01.01", "spec_path": "Spec/design/01-adopted/spec.md", "title": "t",
            "priority": "must", "status": "active", "required_layers": ["unit"],
            "required_layers_source": "inferred_legacy",
            "tests": {"unit": []}, "coverage": {"unit": "MISSING"},
        },
    }
    reqs.update(req_overrides)
    return {
        "schema_version": 4, "collector_version": "x", "generated_at": "2026-01-01T00:00:00Z",
        "source_commit": _COMMIT, "spec_hash": "h", "requirements": reqs,
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
    }


def _artifact_from(manifest: dict, *, source_commit: str = _COMMIT) -> dict:
    out = copy.deepcopy(manifest)
    out["source_commit"] = source_commit
    return out


def _listed(*, artifact_id: int = _ARTIFACT_ID, created_at: str = "2026-09-09T10:00:00Z", **overrides) -> dict:
    entry = {"name": _ARTIFACT_NAME, "expired": False, "id": artifact_id, "created_at": created_at}
    entry.update(overrides)
    return entry


@pytest.fixture(autouse=True)
def _fixed_owner_repo(monkeypatch):
    monkeypatch.setattr(github_api, "owner_repo", lambda project_root: f"{_OWNER}/{_REPO}")


def _verified(run_id: int = _RUN_ID) -> CIVerification:
    return CIVerification("verified", "confirmed", run_id)


def test_unavailable_when_verification_is_not_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: CIVerification("not_verified", "d", None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=_committed_manifest(), project_root=tmp_path)
    assert result.status == "unavailable"
    assert result.requirements is None


def test_unavailable_when_verification_is_no_record(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: CIVerification("no_record", "d", None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=_committed_manifest(), project_root=tmp_path)
    assert result.status == "unavailable"


def test_error_when_verification_itself_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: CIVerification("error", "d", None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=_committed_manifest(), project_root=tmp_path)
    assert result.status == "error"


def test_error_when_owner_repo_unresolvable(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(github_api, "owner_repo", lambda project_root: None)
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=_committed_manifest(), project_root=tmp_path)
    assert result.status == "error"


def test_error_when_artifacts_list_query_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: None)
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=_committed_manifest(), project_root=tmp_path)
    assert result.status == "error"
    assert result.run_id == _RUN_ID


def test_unavailable_when_no_artifact_matches_name(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [{"name": "other", "expired": False}]})
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=_committed_manifest(), project_root=tmp_path)
    assert result.status == "unavailable"


def test_unavailable_when_matching_artifact_is_expired(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(
        m, "_gh_api", lambda path, *, cwd: {"artifacts": [{"name": _ARTIFACT_NAME, "expired": True}]},
    )
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=_committed_manifest(), project_root=tmp_path)
    assert result.status == "unavailable"


def test_error_when_selected_artifact_has_no_valid_id(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(
        m, "_gh_api", lambda path, *, cwd: {"artifacts": [{"name": _ARTIFACT_NAME, "expired": False, "id": None}]},
    )
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=_committed_manifest(), project_root=tmp_path)
    assert result.status == "error"
    assert "id" in result.detail


def test_error_when_listed_artifact_fails_to_download(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [_listed()]})
    monkeypatch.setattr(m, "_download_and_parse_artifact", lambda *a, **k: (None, "boom"))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=_committed_manifest(), project_root=tmp_path)
    assert result.status == "error"


def test_download_is_called_with_the_selected_artifacts_own_id(monkeypatch, tmp_path):
    # Round-3 external code review fix (openai/high + glm/medium, both
    # independently): the artifact SELECTED by `_find_unexpired_artifact`
    # must be the exact one downloaded — no second, independent by-name
    # resolution step that could silently disagree.
    committed = _committed_manifest()
    artifact = _artifact_from(committed)
    artifact["requirements"]["01::FR-01.01"]["coverage"] = {"unit": "ok"}
    artifact["requirements"]["01::FR-01.01"]["tests"] = {"unit": [{"id": "t1", "status": "enabled", "executed": "pass"}]}
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(
        m, "_gh_api", lambda path, *, cwd: {"artifacts": [_listed(artifact_id=987)]},
    )
    calls = []

    def _fake_download(artifact_id, *, owner, repo, cwd):
        calls.append(artifact_id)
        return artifact, None

    monkeypatch.setattr(m, "_download_and_parse_artifact", _fake_download)
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "confirmed"
    assert calls == [987]


def test_confirmed_when_everything_lines_up(monkeypatch, tmp_path):
    committed = _committed_manifest()
    artifact = _artifact_from(committed)
    artifact["requirements"]["01::FR-01.01"]["coverage"] = {"unit": "ok"}
    artifact["requirements"]["01::FR-01.01"]["tests"] = {"unit": [{"id": "t1", "status": "enabled", "executed": "pass"}]}
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [_listed()]})
    monkeypatch.setattr(m, "_download_and_parse_artifact", lambda *a, **k: (artifact, None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "confirmed"
    assert result.run_id == _RUN_ID
    assert result.requirements["01::FR-01.01"]["coverage"] == {"unit": "ok"}


def test_error_when_source_commit_mismatches(monkeypatch, tmp_path):
    """The content-binding forgery test: an artifact fetched from the trusted
    run_id but naming a DIFFERENT commit (cross-attempt mismatch) must never
    be trusted."""
    committed = _committed_manifest()
    artifact = _artifact_from(committed, source_commit="b" * 40)
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [_listed()]})
    monkeypatch.setattr(m, "_download_and_parse_artifact", lambda *a, **k: (artifact, None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "error"


def test_error_when_structural_shape_disagrees(monkeypatch, tmp_path):
    """The content-binding forgery test's other half: same source_commit, but
    the artifact's STRUCTURE (a renamed/added requirement) disagrees with the
    committed manifest -- must never be trusted either."""
    committed = _committed_manifest()
    artifact = _artifact_from(committed)
    artifact["requirements"]["FR-01.99-injected"] = dict(artifact["requirements"]["01::FR-01.01"])
    artifact["requirements"]["FR-01.99-injected"]["id"] = "FR-01.99"
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [_listed()]})
    monkeypatch.setattr(m, "_download_and_parse_artifact", lambda *a, **k: (artifact, None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "error"


def test_error_when_top_level_requirements_is_not_an_object(monkeypatch, tmp_path):
    # Round-3 post-push fix (code-reviewer medium): the `isinstance(...,
    # dict)` guard on the artifact's top-level `requirements` used to run
    # AFTER `structural_diff`, which unconditionally calls
    # `data["requirements"].items()` -- a malformed/adversarial or corrupted
    # upload (`ci.yml`'s `continue-on-error: true` on this step makes this
    # possible) with `requirements` as a list raised an uncaught
    # `AttributeError` here instead of the documented clean `error` outcome.
    committed = _committed_manifest()
    artifact = _artifact_from(committed)
    artifact["requirements"] = []  # malformed: list, not an object
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [_listed()]})
    monkeypatch.setattr(m, "_download_and_parse_artifact", lambda *a, **k: (artifact, None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "error"
    assert "requirements" in result.detail


def test_multiple_matching_artifacts_select_the_newest_id_by_created_at(monkeypatch, tmp_path):
    # External code review (openai/high, P3.5 restart round 2): a re-run can
    # leave more than one artifact with this name under the same run_id --
    # the resolver must pick the NEWEST, not merely the first list entry.
    committed = _committed_manifest()
    artifact = _artifact_from(committed)
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [
        _listed(artifact_id=111, created_at="2026-09-09T10:00:00Z"),
        _listed(artifact_id=222, created_at="2026-09-09T12:00:00Z"),
    ]})
    calls = []

    def _fake_download(artifact_id, *, owner, repo, cwd):
        calls.append(artifact_id)
        return artifact, None

    monkeypatch.setattr(m, "_download_and_parse_artifact", _fake_download)
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "confirmed"
    assert calls == [222]


def test_find_unexpired_artifact_returns_newest_when_created_at_out_of_order():
    artifacts = [
        {"name": "x", "expired": False, "id": 1, "created_at": "2026-09-09T09:00:00Z"},
        {"name": "x", "expired": False, "id": 2, "created_at": "2026-09-09T11:00:00Z"},
        {"name": "x", "expired": False, "id": 3, "created_at": "2026-09-09T10:00:00Z"},
    ]
    picked = m._find_unexpired_artifact(artifacts, "x")
    assert picked["id"] == 2


def test_find_unexpired_artifact_tolerates_a_missing_created_at():
    artifacts = [
        {"name": "x", "expired": False, "id": 1},
        {"name": "x", "expired": False, "id": 2, "created_at": "2026-09-09T11:00:00Z"},
    ]
    picked = m._find_unexpired_artifact(artifacts, "x")
    assert picked["id"] == 2


def test_error_when_execution_tier_coverage_is_not_an_object(monkeypatch, tmp_path):
    # External code review (openai/medium, P3.5 restart round 2):
    # structural_diff deliberately excludes tests/coverage, so a
    # structurally-matching artifact can still carry a malformed shape for
    # them -- must be a clean `error`, never an uncaught exception deep
    # inside evaluate_fr.
    committed = _committed_manifest()
    artifact = _artifact_from(committed)
    artifact["requirements"]["01::FR-01.01"]["coverage"] = ["not", "an", "object"]
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [_listed()]})
    monkeypatch.setattr(m, "_download_and_parse_artifact", lambda *a, **k: (artifact, None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "error"
    assert result.requirements is None


def test_error_when_execution_tier_tests_layer_is_not_a_list(monkeypatch, tmp_path):
    committed = _committed_manifest()
    artifact = _artifact_from(committed)
    artifact["requirements"]["01::FR-01.01"]["tests"] = {"unit": "not-a-list"}
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [_listed()]})
    monkeypatch.setattr(m, "_download_and_parse_artifact", lambda *a, **k: (artifact, None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "error"


def test_error_when_execution_tier_coverage_key_is_deleted_not_merely_falsy(monkeypatch, tmp_path):
    # Round-3 external code review (openai/medium + glm/low, both
    # independently): a structurally-matching artifact whose execution-tier
    # keys are DELETED (a partial/truncated upload, which `continue-on-
    # error: true` makes possible) must be `error`, never silently
    # normalized to `{}` and treated as a genuine, decided "no evidence".
    committed = _committed_manifest()
    artifact = _artifact_from(committed)
    del artifact["requirements"]["01::FR-01.01"]["coverage"]
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: _verified())
    monkeypatch.setattr(m, "_gh_api", lambda path, *, cwd: {"artifacts": [_listed()]})
    monkeypatch.setattr(m, "_download_and_parse_artifact", lambda *a, **k: (artifact, None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "error"
    assert "missing" in result.detail


def test_local_committed_manifest_forgery_never_consulted(monkeypatch, tmp_path):
    """AC3-analogue: a hand-edited committed_manifest claiming 'ok' coverage,
    with no matching CI evidence, must never leak into a `confirmed`
    result's `requirements` -- the artifact is the only source, and it
    disagreeing means `error`, not a silent adoption of the tampered local
    claim."""
    committed = _committed_manifest()
    committed["requirements"]["01::FR-01.01"]["coverage"] = {"unit": "ok"}  # hand-edited, unconfirmed
    monkeypatch.setattr(m, "resolve_ci_verification", lambda *a, **k: CIVerification("no_record", "d", None))
    result = m.resolve_execution_evidence(_COMMIT, committed_manifest=committed, project_root=tmp_path)
    assert result.status == "unavailable"
    assert result.requirements is None


# ------------------------------------------------------------------------- #
# `_execution_shape_error` — direct unit tests
# ------------------------------------------------------------------------- #

def test_execution_shape_error_passes_a_well_formed_requirement():
    raw = {"FR-01.01": {"coverage": {"unit": "ok"}, "tests": {"unit": [{"status": "enabled"}]}}}
    assert m._execution_shape_error(raw, ["FR-01.01"]) is None


def test_execution_shape_error_ignores_ids_outside_expected_ids():
    raw = {
        "FR-01.01": {"coverage": {"unit": "ok"}, "tests": {}},
        "FR-99.99": {"coverage": "not-an-object", "tests": {}},
    }
    assert m._execution_shape_error(raw, ["FR-01.01"]) is None


def test_execution_shape_error_reports_a_non_dict_node():
    raw = {"FR-01.01": "not-a-node"}
    err = m._execution_shape_error(raw, ["FR-01.01"])
    assert err is not None and "FR-01.01" in err


# ------------------------------------------------------------------------- #
# `_download_and_parse_artifact` — direct subprocess-level tests
# ------------------------------------------------------------------------- #

def _zip_bytes(filename: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


def test_download_returns_none_and_detail_on_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(cmd, *, cwd, stdout, stderr, timeout, shell):
        stdout.write(b"")
        return subprocess.CompletedProcess(cmd, returncode=1, stdout=None, stderr=b"not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    artifact, detail = m._download_and_parse_artifact(_ARTIFACT_ID, owner=_OWNER, repo=_REPO, cwd=tmp_path)
    assert artifact is None
    assert "not found" in detail


def test_download_returns_none_when_gh_binary_missing(monkeypatch, tmp_path):
    def fake_run(*a, **k):
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    artifact, detail = m._download_and_parse_artifact(_ARTIFACT_ID, owner=_OWNER, repo=_REPO, cwd=tmp_path)
    assert artifact is None
    assert detail is not None


def test_download_extracts_and_parses_the_real_zip(monkeypatch, tmp_path):
    payload = _zip_bytes(m._MANIFEST_FILENAME, b'{"source_commit": "x"}')
    requested_paths = []

    def fake_run(cmd, *, cwd, stdout, stderr, timeout, shell):
        requested_paths.append(cmd[-1])
        stdout.write(payload)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=None, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    artifact, detail = m._download_and_parse_artifact(_ARTIFACT_ID, owner=_OWNER, repo=_REPO, cwd=tmp_path)
    assert detail is None
    assert artifact == {"source_commit": "x"}
    assert requested_paths == [f"repos/{_OWNER}/{_REPO}/actions/artifacts/{_ARTIFACT_ID}/zip"]


def test_download_reports_a_zip_missing_the_expected_file(monkeypatch, tmp_path):
    payload = _zip_bytes("some-other-file.json", b"{}")

    def fake_run(cmd, *, cwd, stdout, stderr, timeout, shell):
        stdout.write(payload)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=None, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    artifact, detail = m._download_and_parse_artifact(_ARTIFACT_ID, owner=_OWNER, repo=_REPO, cwd=tmp_path)
    assert artifact is None
    assert m._MANIFEST_FILENAME in detail


def test_download_reports_a_corrupt_zip(monkeypatch, tmp_path):
    def fake_run(cmd, *, cwd, stdout, stderr, timeout, shell):
        stdout.write(b"not a real zip file")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=None, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    artifact, detail = m._download_and_parse_artifact(_ARTIFACT_ID, owner=_OWNER, repo=_REPO, cwd=tmp_path)
    assert artifact is None
    assert detail is not None
