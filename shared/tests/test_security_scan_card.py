"""AC-6 producer test: the collapsed security scan card lands in triage.jsonl.

Sibling of ``test_security_triage_emit.py``, which covers the per-finding
enumeration. This covers the ONE card per repository that carries the
per-severity split, what the scan did not check, and the scope question — the
thing the operator actually receives and executes.

Lives under ``shared/tests`` for the same reason the sibling does: importing
the shared ``triage`` module from the security plugin's own pytest session hits
the ADR-044 ``lib`` namespace collision.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
_PLUGIN = _WORKTREE / "plugins" / "shipwright-security"
for _p in (_SHARED_SCRIPTS, _PLUGIN / "scripts" / "lib", _PLUGIN / "scripts" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rsr = _load(
    "run_scan_and_report_for_card_test",
    _PLUGIN / "scripts" / "tools" / "run_scan_and_report.py",
)

from triage import read_all_items  # noqa: E402

_FINDING = {
    "id": "f1", "severity": "high", "type": "sast", "rule": "r1",
    "source": "semgrep", "affected_file": "a.py", "affected_line": 3,
    "description": "boom",
}


class _Backend:
    name = "oss"

    def __init__(self, caps: set[str], findings: list[dict] | None = None) -> None:
        self.capabilities = caps
        self.scan_errors: list[dict] = []
        self._findings = findings or []

    def scan(self, target, scan_types=None):  # noqa: ARG002
        return list(self._findings)


def _scan(tmp_path: Path, caps: set[str], findings: list[dict]) -> None:
    with patch.object(rsr, "get_backend", return_value=_Backend(caps, findings)):
        rsr.run(project_root=tmp_path, repo="o/r")


def _cards(project: Path) -> list[dict]:
    return [
        i for i in read_all_items(project)
        if str(i.get("dedupKey", "")).startswith("security-scan:")
    ]


@pytest.mark.covers("FR-01.07")
def test_scan_emits_exactly_one_card(tmp_path: Path) -> None:
    _scan(tmp_path, {"sast"}, [_FINDING, {**_FINDING, "rule": "r2"}])
    assert len(_cards(tmp_path)) == 1


@pytest.mark.covers("FR-01.07")
def test_card_states_the_counts_per_severity(tmp_path: Path) -> None:
    findings = [
        {**_FINDING, "severity": "critical", "rule": "c1", "affected_line": 1},
        {**_FINDING, "severity": "critical", "rule": "c2", "affected_line": 2},
        {**_FINDING, "severity": "low", "rule": "l1", "affected_line": 3},
    ]
    _scan(tmp_path, {"sast"}, findings)
    payload = _cards(tmp_path)[0]["launchPayload"]
    assert "critical: 2" in payload
    assert "low: 1" in payload


@pytest.mark.covers("FR-01.07")
def test_card_asks_how_far_to_go(tmp_path: Path) -> None:
    findings = [
        {**_FINDING, "severity": "critical", "rule": "c1", "affected_line": 1},
        {**_FINDING, "severity": "low", "rule": "l1", "affected_line": 2},
    ]
    _scan(tmp_path, {"sast"}, findings)
    payload = _cards(tmp_path)[0]["launchPayload"]
    assert "everything (2)" in payload
    assert "critical and above (1)" in payload
    assert payload.count("?") >= 1


@pytest.mark.covers("FR-01.07")
def test_card_names_what_was_not_checked(tmp_path: Path) -> None:
    _scan(tmp_path, {"sast"}, [_FINDING])
    card = _cards(tmp_path)[0]
    assert "Leaked secrets" in card["launchPayload"]
    assert "not checked" in card["detail"].lower()


@pytest.mark.covers("FR-01.07")
def test_card_report_path_uses_posix_separators(tmp_path: Path) -> None:
    """The payload is pasted into a shell/prompt — a backslash path would not
    resolve there, and on POSIX it is not even a path separator."""
    _scan(tmp_path, {"sast"}, [_FINDING])
    assert ".shipwright/securityreports/latest.md" in _cards(tmp_path)[0]["launchPayload"]


@pytest.mark.covers("FR-01.07")
def test_clean_scan_emits_no_card(tmp_path: Path) -> None:
    _scan(tmp_path, {"sast"}, [])
    assert _cards(tmp_path) == []


@pytest.mark.covers("FR-01.07")
def test_card_is_deduped_across_repeat_scans(tmp_path: Path) -> None:
    """One card per repository — a re-scan must not stack a second copy."""
    _scan(tmp_path, {"sast"}, [_FINDING])
    _scan(tmp_path, {"sast"}, [_FINDING])
    assert len(_cards(tmp_path)) == 1


@pytest.mark.covers("FR-01.07")
def test_card_coexists_with_the_per_finding_enumeration(tmp_path: Path) -> None:
    """The card ADDS the severity split; it does not replace the mirrors the
    report generator emits."""
    import generate_security_report as gsr  # noqa: PLC0415

    gsr._emit_findings_to_triage(tmp_path, [_FINDING], run_id="r1")
    _scan(tmp_path, {"sast"}, [_FINDING])
    keys = {i.get("dedupKey") for i in read_all_items(tmp_path)}
    assert "security-scan:o/r" in keys
    assert "semgrep:r1:a.py:3" in keys
