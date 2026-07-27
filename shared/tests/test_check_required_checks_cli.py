"""The required-check producer's I/O layer and its exit codes.

@FR-01.17

``test_required_checks_drift.py`` covers the pure comparison. Everything that
made the first draft wrong lives HERE instead — in what the producer decides
after talking to the host:

- **An unprotected repo is a finding, not an error.** Requiring nothing is the
  loudest thing this tool can report: every check runs and gates nothing. The
  first draft raised on it, so the producer was blind exactly where it mattered
  most (found by both external reviewers).
- **A 404 only means "no such policy" once the repo is known readable.** A typo'd
  slug 404s on every endpoint too, and reading that as "protects nothing" would
  report every check as unenforced — a producer crying wolf at full volume.
- **`gh` missing or hanging must exit 2, not traceback.** Neither raises
  CalledProcessError, so neither was caught; the documented exit code was a
  fiction for the most common user failure.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _REPO_ROOT / "shared" / "scripts"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


def _load():
    """Load the tool by path — it is a script, not an importable module."""
    path = _TOOLS / "tools" / "check_required_checks.py"
    spec = importlib.util.spec_from_file_location("_check_required_checks", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_check_required_checks"] = module
    spec.loader.exec_module(module)
    return module


crc = _load()


class _Resp:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _gh_router(routes: dict[str, _Resp], recorder: list[str] | None = None):
    """Fake `subprocess.run` dispatching on the API path in the argv."""

    def _run(argv, **kwargs):
        if argv and argv[0] == "git":
            return _Resp(0, "https://github.com/o/r.git\n")
        endpoint = argv[-1]
        if recorder is not None:
            recorder.append(endpoint)
        for pattern, resp in routes.items():
            if endpoint.endswith(pattern):
                return resp
        raise AssertionError(f"unrouted gh call: {endpoint}")

    return _run


_REPO_OK = _Resp(0, json.dumps({"default_branch": "main"}))
_NOT_FOUND = _Resp(1, "", "gh: Not Found (HTTP 404)")
_FORBIDDEN = _Resp(1, "", "gh: Resource not accessible (HTTP 403)")


# ---------------------------------------------------------------------------
# _gh — the two failures users actually hit
# ---------------------------------------------------------------------------


def test_missing_gh_binary_is_a_controlled_error(monkeypatch) -> None:
    def _boom(*a, **k):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(crc.subprocess, "run", _boom)
    with pytest.raises(crc.GhError) as excinfo:
        crc._gh(["api", "repos/o/r"])
    assert "not installed" in str(excinfo.value)
    assert excinfo.value.status is None


def test_gh_timeout_is_a_controlled_error(monkeypatch) -> None:
    def _hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="gh", timeout=60)

    monkeypatch.setattr(crc.subprocess, "run", _hang)
    with pytest.raises(crc.GhError) as excinfo:
        crc._gh(["api", "repos/o/r"])
    assert "timed out" in str(excinfo.value)


def test_http_status_is_carried_off_stderr(monkeypatch) -> None:
    """404-vs-403 is the whole basis for 'no policy' vs 'could not ask'."""
    monkeypatch.setattr(crc.subprocess, "run", lambda *a, **k: _NOT_FOUND)
    with pytest.raises(crc.GhError) as excinfo:
        crc._gh(["api", "repos/o/r"])
    assert excinfo.value.status == 404


def test_a_failure_with_no_http_code_carries_no_status(monkeypatch) -> None:
    monkeypatch.setattr(
        crc.subprocess, "run", lambda *a, **k: _Resp(1, "", "dial tcp: no route to host")
    )
    with pytest.raises(crc.GhError) as excinfo:
        crc._gh(["api", "repos/o/r"])
    assert excinfo.value.status is None


# ---------------------------------------------------------------------------
# fetch_configured_contexts — readable vs empty
# ---------------------------------------------------------------------------


def test_a_repo_that_requires_nothing_reads_as_empty_not_unreadable(monkeypatch) -> None:
    """The regression both external reviewers caught. THE test in this file."""
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "/rules/branches/main": _Resp(0, "[]"),
        "/branches/main/protection": _NOT_FOUND,  # "Branch not protected"
    }))
    assert crc.fetch_configured_contexts("o/r", "main") == []


def test_empty_configured_set_makes_every_check_unenforced() -> None:
    """...and that empty set must read as total drift, never as 'in sync'."""
    result = crc.compare_required_checks(["Build", "Test"], [])
    assert not result["in_sync"]
    assert result["unenforced"] == ["Build", "Test"]
    assert result["phantom"] == []


def test_contexts_come_from_rulesets(monkeypatch) -> None:
    rules = [
        {"type": "pull_request", "parameters": {}},
        {"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "Build"}, {"context": "Scan"}]}},
    ]
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "/rules/branches/main": _Resp(0, json.dumps(rules)),
        "/branches/main/protection": _NOT_FOUND,
    }))
    assert sorted(crc.fetch_configured_contexts("o/r", "main")) == ["Build", "Scan"]


def test_classic_branch_protection_is_still_read(monkeypatch) -> None:
    prot = {"required_status_checks": {"contexts": ["Legacy gate"]}}
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "/rules/branches/main": _Resp(0, "[]"),
        "/branches/main/protection": _Resp(0, json.dumps(prot)),
    }))
    assert crc.fetch_configured_contexts("o/r", "main") == ["Legacy gate"]


def test_both_mechanisms_union(monkeypatch) -> None:
    rules = [{"type": "required_status_checks",
              "parameters": {"required_status_checks": [{"context": "Build"}]}}]
    prot = {"required_status_checks": {"contexts": ["Legacy gate"]}}
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "/rules/branches/main": _Resp(0, json.dumps(rules)),
        "/branches/main/protection": _Resp(0, json.dumps(prot)),
    }))
    assert sorted(crc.fetch_configured_contexts("o/r", "main")) == ["Build", "Legacy gate"]


def test_neither_mechanism_readable_raises(monkeypatch) -> None:
    """403 on both is 'I could not ask' — never compared against."""
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "/rules/branches/main": _FORBIDDEN,
        "/branches/main/protection": _FORBIDDEN,
    }))
    with pytest.raises(RuntimeError, match="could not read"):
        crc.fetch_configured_contexts("o/r", "main")


def test_one_mechanism_unreadable_does_not_sink_the_other(monkeypatch) -> None:
    rules = [{"type": "required_status_checks",
              "parameters": {"required_status_checks": [{"context": "Build"}]}}]
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "/rules/branches/main": _Resp(0, json.dumps(rules)),
        "/branches/main/protection": _FORBIDDEN,
    }))
    assert crc.fetch_configured_contexts("o/r", "main") == ["Build"]


def test_unparseable_response_is_not_read_as_empty(monkeypatch) -> None:
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "/rules/branches/main": _Resp(0, "<html>proxy error</html>"),
        "/branches/main/protection": _Resp(0, "<html>proxy error</html>"),
    }))
    with pytest.raises(RuntimeError, match="could not read"):
        crc.fetch_configured_contexts("o/r", "main")


def test_the_policy_is_read_for_the_named_branch(monkeypatch) -> None:
    """Ref scoping: a release-branch ruleset must not be compared against main.

    Delegated to the host — /rules/branches/<ref> returns only the rules GitHub
    itself evaluates for that ref — so what this pins is that the branch really
    reaches the URL.
    """
    seen: list[str] = []
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "/rules/branches/release/v2": _Resp(0, "[]"),
        "/branches/release/v2/protection": _NOT_FOUND,
    }, recorder=seen))
    crc.fetch_configured_contexts("o/r", "release/v2")
    assert any(e.endswith("/rules/branches/release/v2") for e in seen), seen
    assert not any("branches/main" in e for e in seen), seen


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


def test_unreachable_repo_exits_2_before_any_policy_lookup(monkeypatch, capsys) -> None:
    """A typo'd slug must not be read as 'this repo protects nothing'."""
    seen: list[str] = []
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({"repos/o/r": _NOT_FOUND},
                                                          recorder=seen))
    assert crc.main(["--project-root", str(_REPO_ROOT), "--repo", "o/r", "--no-file"]) == 2
    assert "[required-checks]" in capsys.readouterr().err
    assert not any("/rules/branches" in e for e in seen), (
        "policy was queried for a repo we could not even read"
    )


def test_missing_gh_exits_2_without_a_traceback(monkeypatch, capsys) -> None:
    def _run(argv, **kwargs):
        if argv and argv[0] == "git":
            return _Resp(0, "https://github.com/o/r.git\n")
        raise FileNotFoundError("gh")

    monkeypatch.setattr(crc.subprocess, "run", _run)
    assert crc.main(["--project-root", str(_REPO_ROOT), "--no-file"]) == 2
    assert "not installed" in capsys.readouterr().err


def test_in_sync_repo_exits_0_and_files_nothing(monkeypatch, capsys, tmp_path) -> None:
    derived = crc.all_workflow_check_names(_REPO_ROOT)
    rules = [{"type": "required_status_checks", "parameters": {
        "required_status_checks": [{"context": c} for c in derived]}}]
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "repos/o/r": _REPO_OK,
        "/rules/branches/main": _Resp(0, json.dumps(rules)),
        "/branches/main/protection": _NOT_FOUND,
    }))
    filed: list[dict] = []
    monkeypatch.setattr(crc, "append_triage_item_idempotent",
                        lambda *a, **k: filed.append(k) or "trg-test")
    rc = crc.main(["--project-root", str(_REPO_ROOT), "--repo", "o/r", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["in_sync"] is True
    assert filed == [], "an in-sync repo must file nothing"


def test_drift_files_one_item_keyed_on_repo_and_branch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(crc.subprocess, "run", _gh_router({
        "repos/o/r": _REPO_OK,
        "/rules/branches/main": _Resp(0, "[]"),      # requires nothing
        "/branches/main/protection": _NOT_FOUND,
    }))
    filed: list[dict] = []
    monkeypatch.setattr(crc, "append_triage_item_idempotent",
                        lambda *a, **k: filed.append(k) or "trg-test")
    assert crc.main(["--project-root", str(_REPO_ROOT), "--repo", "o/r"]) == 0
    capsys.readouterr()
    assert len(filed) == 1
    assert filed[0]["source"] == "required-checks"
    assert filed[0]["to_outbox"] is True
    assert "o/r@main" in filed[0]["dedup_key"], filed[0]["dedup_key"]
