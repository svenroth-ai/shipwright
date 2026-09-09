"""Tests for shared/scripts/ci_provenance.py's `_gh_api()` transport helper
and its `cwd` binding — split out of test_ci_provenance.py (P3.4c,
iterate-2026-09-08-ci-provenance-attestation) once that file crossed the
300-line guideline. test_ci_provenance.py covers `resolve_ci_verification()`
outcomes; this file covers the subprocess plumbing underneath it, which every
outcome-level test monkeypatches past.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import ci_provenance  # noqa: E402
import github_api  # noqa: E402

_COMMIT = "a" * 40
_OWNER, _REPO = "acme", "foo"
_DEFAULT_BRANCH = "main"


@pytest.fixture(autouse=True)
def _fixed_owner_repo(monkeypatch):
    monkeypatch.setattr(github_api, "owner_repo", lambda project_root: f"{_OWNER}/{_REPO}")


def test_gh_api_real_subprocess_argv_and_cwd(monkeypatch, tmp_path):
    """Direct coverage of `_gh_api`'s own subprocess construction — every
    other test monkeypatches past it entirely."""
    captured = {}

    class _FakeCompleted:
        returncode = 0
        stdout = '{"ok": true}'

    def fake_run(argv, *, cwd, capture_output, text, timeout, encoding, errors):
        captured["argv"] = argv
        captured["cwd"] = cwd
        captured["timeout"] = timeout
        return _FakeCompleted()

    monkeypatch.setattr(ci_provenance.subprocess, "run", fake_run)
    result = ci_provenance._gh_api("repos/acme/foo", cwd=tmp_path)

    assert result == {"ok": True}
    assert captured["argv"] == ["gh", "api", "repos/acme/foo"]
    assert captured["cwd"] == tmp_path
    assert captured["timeout"] == ci_provenance._TIMEOUT_SECONDS


def test_gh_api_returns_none_when_gh_binary_is_missing(monkeypatch, tmp_path):
    """Step 7.5 empirical probe: `subprocess.run` raises `FileNotFoundError`
    (an `OSError` subclass) when the `gh` executable isn't on PATH at all —
    distinct from the mocked-`returncode`/bad-JSON paths below, which never
    exercise the `except (OSError, ...)` branch."""

    def raise_not_found(*args, **kwargs):
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(ci_provenance.subprocess, "run", raise_not_found)
    assert ci_provenance._gh_api("repos/acme/foo", cwd=tmp_path) is None


def test_gh_api_returns_none_on_nonzero_exit_and_bad_json(monkeypatch, tmp_path):
    class _FailedCompleted:
        returncode = 1
        stdout = "not json"

    monkeypatch.setattr(ci_provenance.subprocess, "run", lambda *a, **k: _FailedCompleted())
    assert ci_provenance._gh_api("repos/acme/foo", cwd=tmp_path) is None

    class _BadJsonCompleted:
        returncode = 0
        stdout = "{not valid json"

    monkeypatch.setattr(ci_provenance.subprocess, "run", lambda *a, **k: _BadJsonCompleted())
    assert ci_provenance._gh_api("repos/acme/foo", cwd=tmp_path) is None


def test_gh_api_passes_project_root_as_cwd_not_process_cwd(monkeypatch, tmp_path):
    """The exact bug class Internal + External Review flagged for
    `github_api.default_branch()`: repo context must come from `project_root`,
    never the process's own cwd."""
    seen_cwds: list = []

    def fake_gh_api(path: str, *, cwd):
        seen_cwds.append(cwd)
        if "/actions/" not in path:
            return {"default_branch": _DEFAULT_BRANCH}
        if "/runs?" in path:
            return {"workflow_runs": []}
        return None

    monkeypatch.setattr(ci_provenance, "_gh_api", fake_gh_api)
    ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert seen_cwds
    assert all(cwd == tmp_path for cwd in seen_cwds)
