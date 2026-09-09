"""`ci_provenance_check.py` CLI contract (P3.4c,
iterate-2026-09-08-ci-provenance-attestation).

Covers the status-to-exit-code mapping in-process (predicate mocked at the
module-object boundary), AND a real subprocess invocation — Internal Plan
Review's warning that `shared/tests`'s conftest sys.path setup can mask
exactly the import-path bug class this module's flat-module placement
(`shared/scripts/ci_provenance.py`, imported via `sys.path.insert` from a
`tools/` script — see `ci_manifest_drift_check.py`'s own docstring for the
precedent of this exact failure mode) is designed to avoid.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.ci_provenance_check as mod  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CLI_PATH = _REPO_ROOT / "shared" / "scripts" / "tools" / "ci_provenance_check.py"
_COMMIT = "b" * 40


class _FakeResult:
    def __init__(self, status: str, detail: str = "detail", run_id=None):
        self.status = status
        self.detail = detail
        self.run_id = run_id


def _run_cli(monkeypatch, capsys, status: str, run_id=None) -> tuple[int, dict]:
    # Bypass the real `git rev-parse` expansion — these tests exercise the
    # status-to-exit-code mapping, not commit resolution (that has its own
    # tests below).
    monkeypatch.setattr(mod, "_resolve_full_sha", lambda commit, project_root: commit)
    monkeypatch.setattr(mod, "resolve_ci_verification", lambda commit, *, project_root: _FakeResult(status, run_id=run_id))
    exit_code = mod.main(["verify", "--commit", _COMMIT, "--project-root", "."])
    captured = json.loads(capsys.readouterr().out)
    return exit_code, captured


def test_verified_maps_to_exit_0(monkeypatch, capsys):
    exit_code, payload = _run_cli(monkeypatch, capsys, "verified", run_id=42)
    assert exit_code == 0
    assert payload == {"status": "verified", "detail": "detail", "run_id": 42}


def test_not_verified_maps_to_exit_3(monkeypatch, capsys):
    exit_code, payload = _run_cli(monkeypatch, capsys, "not_verified")
    assert exit_code == 3
    assert payload["status"] == "not_verified"


def test_no_record_maps_to_exit_4(monkeypatch, capsys):
    exit_code, payload = _run_cli(monkeypatch, capsys, "no_record")
    assert exit_code == 4
    assert payload["status"] == "no_record"


def test_error_maps_to_exit_2_distinct_from_no_record(monkeypatch, capsys):
    exit_code, payload = _run_cli(monkeypatch, capsys, "error")
    assert exit_code == 2
    assert payload["status"] == "error"
    assert exit_code != 4  # error and no_record must never collapse to the same code


def test_real_subprocess_invocation_starts_cleanly():
    """The bug class this test exists to catch never surfaces via an
    in-process import under pytest's own sys.path side effects — only a real
    child process reproduces it (see module docstring). `not-a-valid-sha` is
    also unresolvable by `git rev-parse`, so this doubles as a real (not
    monkeypatched) exercise of the rev-parse-fails path."""
    result = subprocess.run(
        [sys.executable, str(_CLI_PATH), "verify", "--commit", "not-a-valid-sha", "--project-root", str(_REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"


def test_resolve_full_sha_expands_head_via_real_git():
    """Real `git rev-parse` invocation (no monkeypatch): `HEAD` in this repo
    resolves to a genuine 40-char SHA — the exact expansion the spec's
    '## Design (final)' promises and an abbreviated `head_sha` query
    would otherwise silently under-match."""
    sha = mod._resolve_full_sha("HEAD", _REPO_ROOT)
    assert sha is not None
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_resolve_full_sha_returns_none_for_unresolvable_ref():
    assert mod._resolve_full_sha("not-a-real-ref-xyz", _REPO_ROOT) is None


def test_unresolvable_commit_maps_to_cli_exit_2(monkeypatch, capsys):
    """When `git rev-parse` cannot resolve `--commit`, the CLI must exit 2
    with status=error WITHOUT ever calling `resolve_ci_verification` — an
    unresolvable ref is a `git` failure, not a GitHub query outcome."""
    called = []
    monkeypatch.setattr(mod, "_resolve_full_sha", lambda commit, project_root: None)
    monkeypatch.setattr(mod, "resolve_ci_verification", lambda commit, *, project_root: called.append(commit))

    exit_code = mod.main(["verify", "--commit", "bogus", "--project-root", "."])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "error"
    assert called == []
