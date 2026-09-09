"""``ci_execution_evidence_check.py`` CLI contract (P3.5 restart round 2,
AC-R16, mirrors ``test_ci_provenance_check.py``'s own shape).

Covers commit-resolution, manifest-read, and the resolver call in-process
(mocked at the module-object boundary), plus one real subprocess invocation
for the same import-path bug class ``test_ci_provenance_check.py`` guards
against (flat module under ``shared/scripts/``, imported via
``sys.path.insert`` from a ``tools/`` script).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.ci_execution_evidence_check as mod  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CLI_PATH = _REPO_ROOT / "shared" / "scripts" / "tools" / "ci_execution_evidence_check.py"
_COMMIT = "c" * 40


class _FakeEvidence:
    def __init__(self, status: str, detail: str = "detail", run_id=None, requirements=None):
        self.status = status
        self.detail = detail
        self.run_id = run_id
        self.requirements = requirements


def _run_cli(monkeypatch, capsys, *, status: str, run_id=None, requirements=None) -> tuple[int, dict]:
    monkeypatch.setattr(mod, "_resolve_full_sha", lambda commit, project_root: commit)
    monkeypatch.setattr(mod, "_read_manifest_at", lambda sha, project_root: ({"requirements": {}}, None))
    monkeypatch.setattr(
        mod, "resolve_execution_evidence",
        lambda commit, *, committed_manifest, project_root: _FakeEvidence(
            status, run_id=run_id, requirements=requirements,
        ),
    )
    exit_code = mod.main(["check", "--commit", _COMMIT, "--project-root", "."])
    captured = json.loads(capsys.readouterr().out)
    return exit_code, captured


def test_confirmed_always_exits_zero_and_reports_fr_count(monkeypatch, capsys):
    exit_code, payload = _run_cli(
        monkeypatch, capsys, status="confirmed", run_id=42,
        requirements={"FR-01.01": {"tests": {}, "coverage": {}}, "FR-01.02": {"tests": {}, "coverage": {}}},
    )
    assert exit_code == 0
    assert payload == {"status": "confirmed", "detail": "detail", "run_id": 42, "fr_count": 2}


def test_unavailable_always_exits_zero_with_null_fr_count(monkeypatch, capsys):
    exit_code, payload = _run_cli(monkeypatch, capsys, status="unavailable")
    assert exit_code == 0
    assert payload["status"] == "unavailable"
    assert payload["fr_count"] is None


def test_error_from_the_resolver_still_exits_zero_this_is_a_pure_diagnostic(monkeypatch, capsys):
    # This CLI never gates anything -- unlike promote_required_layers.py
    # (which exits 2 on `status=="error"`), this one always reports and
    # always exits 0.
    exit_code, payload = _run_cli(monkeypatch, capsys, status="error")
    assert exit_code == 0
    assert payload["status"] == "error"
    assert payload["fr_count"] is None


def test_confirmed_with_none_requirements_is_a_null_fr_count_not_a_crash(monkeypatch, capsys):
    # Defensive: a `confirmed` status is contractually paired with a non-None
    # `requirements` dict, but this diagnostic must not crash even if a
    # future resolver bug violates that.
    exit_code, payload = _run_cli(monkeypatch, capsys, status="confirmed", run_id=1, requirements=None)
    assert exit_code == 0
    assert payload["fr_count"] is None


def test_unresolvable_commit_reports_error_without_touching_git_show_or_the_resolver(monkeypatch, capsys):
    read_manifest_called = []
    resolver_called = []
    monkeypatch.setattr(mod, "_resolve_full_sha", lambda commit, project_root: None)
    monkeypatch.setattr(mod, "_read_manifest_at", lambda sha, project_root: read_manifest_called.append(sha))
    monkeypatch.setattr(
        mod, "resolve_execution_evidence",
        lambda *a, **k: resolver_called.append(True),
    )

    exit_code = mod.main(["check", "--commit", "bogus", "--project-root", "."])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "error"
    assert "could not resolve" in payload["detail"]
    assert payload["run_id"] is None
    assert payload["fr_count"] is None
    assert read_manifest_called == []
    assert resolver_called == []


def test_manifest_read_failure_reports_error_without_calling_the_resolver(monkeypatch, capsys):
    resolver_called = []
    monkeypatch.setattr(mod, "_resolve_full_sha", lambda commit, project_root: commit)
    monkeypatch.setattr(mod, "_read_manifest_at", lambda sha, project_root: (None, "manifest not found at this commit"))
    monkeypatch.setattr(mod, "resolve_execution_evidence", lambda *a, **k: resolver_called.append(True))

    exit_code = mod.main(["check", "--commit", _COMMIT, "--project-root", "."])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "error"
    assert payload["detail"] == "manifest not found at this commit"
    assert resolver_called == []


def test_real_subprocess_invocation_starts_cleanly_and_still_exits_zero():
    """Same rationale as `test_ci_provenance_check.py`'s twin test: the
    import-path bug class this module's flat placement guards against only
    surfaces via a real child process. `not-a-valid-sha` doubles as a real
    (unmocked) exercise of the rev-parse-fails path -- and, being a pure
    diagnostic, this CLI exits 0 even here (unlike `ci_provenance_check.py`,
    which exits 2 on the analogous case)."""
    result = subprocess.run(
        [sys.executable, str(_CLI_PATH), "check", "--commit", "not-a-valid-sha", "--project-root", str(_REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"


def test_resolve_full_sha_expands_head_via_real_git():
    sha = mod._resolve_full_sha("HEAD", _REPO_ROOT)
    assert sha is not None
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_resolve_full_sha_returns_none_for_unresolvable_ref():
    assert mod._resolve_full_sha("not-a-real-ref-xyz", _REPO_ROOT) is None


def test_read_manifest_at_real_head_reads_the_actual_committed_manifest():
    sha = mod._resolve_full_sha("HEAD", _REPO_ROOT)
    manifest, error = mod._read_manifest_at(sha, _REPO_ROOT)
    assert error is None
    assert isinstance(manifest, dict)
    assert "requirements" in manifest


def test_read_manifest_at_nonexistent_sha_returns_a_detail_not_a_crash():
    manifest, error = mod._read_manifest_at("f" * 40, _REPO_ROOT)
    assert manifest is None
    assert error is not None
