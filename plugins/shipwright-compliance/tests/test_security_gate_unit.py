"""In-process tests for ``lib/security_gate`` — the release gate's decision logic.

The sibling suites drive the hook through ``subprocess``, which proves the real
end-to-end wiring but is invisible to coverage.py (the child process is not
instrumented), so the diff-coverage gate read the module as 0%. These call the
functions directly: better-targeted assertions, and the coverage the gate needs.

Together they answer different questions — *does the shipped script behave?*
(subprocess) versus *does each branch of the decision behave?* (here).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Two ``lib`` packages co-exist in this repo (shared/scripts/lib and this
# plugin's). Drop any cached ``lib.*`` an alphabetically-earlier sibling loaded
# from the SHARED tree, or ``from lib.security_gate`` resolves to the wrong one
# (ADR-045).
for _stale in [k for k in list(sys.modules) if k == "lib" or k.startswith("lib.")]:
    del sys.modules[_stale]
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from lib import security_gate as _sg  # noqa: E402
from lib.security_gate import (  # noqa: E402
    CI_SECURITY_REL,
    UNUSABLE,
    critical_count,
    decide,
    load_threshold,
    read_security_summary,
)

SUMMARY_REL = Path(".shipwright") / "compliance" / "ci-security.json"


def _write(root: Path, payload, *, raw: str | None = None) -> Path:
    target = root / SUMMARY_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(raw if raw is not None else json.dumps(payload),
                      encoding="utf-8")
    return target


def _summary(**over) -> dict:
    base = {
        "schema": 1, "scan_date": "2026-07-28T07:51:37Z", "source": "security.yml#1",
        "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "total": 0, "open_high_critical": 0, "critical_gate": "pass",
        "prompt_injection": 0, "degraded": False,
    }
    base.update(over)
    return base


class TestReadSecuritySummary:
    def test_absent_is_none(self, tmp_path: Path):
        assert read_security_summary(tmp_path) is None

    def test_valid_summary_is_returned(self, tmp_path: Path):
        _write(tmp_path, _summary())
        assert read_security_summary(tmp_path)["critical_gate"] == "pass"

    def test_malformed_json_is_unusable(self, tmp_path: Path):
        _write(tmp_path, None, raw='{"schema": 1, "by_sever')
        assert read_security_summary(tmp_path) is UNUSABLE

    def test_non_object_is_unusable(self, tmp_path: Path):
        _write(tmp_path, [1, 2, 3])
        assert read_security_summary(tmp_path) is UNUSABLE

    def test_directory_at_the_path_is_unusable(self, tmp_path: Path):
        (tmp_path / SUMMARY_REL).mkdir(parents=True)
        assert read_security_summary(tmp_path) is UNUSABLE

    def test_undecodable_bytes_are_unusable(self, tmp_path: Path):
        target = tmp_path / SUMMARY_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\xff\xfe\x00\x00 not utf-8")
        assert read_security_summary(tmp_path) is UNUSABLE

    def test_a_stat_error_is_unusable_not_absent(self, tmp_path: Path, monkeypatch):
        """PermissionError etc. must NOT read as 'never scanned' — that is the
        fail-open `Path.exists()` would have produced.

        Patches the MODULE OBJECT, never the dotted string ``"lib.security_gate…"``:
        monkeypatch re-imports a string target, and two ``lib`` packages co-exist
        here, so in a full-suite run that resolves to the shared one and raises
        ModuleNotFoundError (ADR-045). Observed exactly that, green in isolation.
        """
        _write(tmp_path, _summary())
        real = _sg.os.stat

        def boom(path, *a, **kw):
            if str(path).endswith("ci-security.json"):
                raise PermissionError(13, "denied")
            return real(path, *a, **kw)

        monkeypatch.setattr(_sg.os, "stat", boom)
        assert read_security_summary(tmp_path) is UNUSABLE


class TestCriticalCount:
    def test_reads_by_severity(self):
        assert critical_count(_summary(by_severity={"critical": 4})) == 4

    def test_zero_is_zero_not_falsy_none(self):
        assert critical_count(_summary()) == 0

    @pytest.mark.parametrize("bad", [None, "3", True, -1, {"critical": "x"}])
    def test_unusable_shapes_yield_none(self, bad):
        payload = _summary(by_severity=bad if isinstance(bad, dict)
                           else {"critical": bad})
        assert critical_count(payload) is None

    def test_missing_by_severity_yields_none(self):
        s = _summary()
        del s["by_severity"]
        assert critical_count(s) is None

    def test_critical_gate_is_never_cast_to_a_count(self):
        """A boolean verdict is not a number. Folding `fail` in as 1 would let a
        threshold of 1 allow what the producer refused."""
        s = _summary(critical_gate="fail")
        del s["by_severity"]
        assert critical_count(s) is None


class TestLoadThreshold:
    def test_absent_config_is_zero(self, tmp_path: Path):
        assert load_threshold(tmp_path) == 0

    def test_reads_the_configured_value(self, tmp_path: Path):
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps({"enforcement": {"allowed_critical_findings": 3}}),
            encoding="utf-8")
        assert load_threshold(tmp_path) == 3

    @pytest.mark.parametrize("cfg", [
        "[]",                                          # top-level list
        '{"enforcement": null}',                       # non-dict enforcement
        '{"enforcement": []}',
        '{"enforcement": {"allowed_critical_findings": "lots"}}',
        '{"enforcement": {"allowed_critical_findings": -3}}',
        '{"enforcement": {"allowed_critical_findings": true}}',
        "not json at all",
    ])
    def test_every_malformed_shape_coerces_to_zero(self, tmp_path: Path, cfg: str):
        """A hand-edited config must never widen the gate, and must never raise
        into the hook's fail-open wrapper."""
        (tmp_path / "shipwright_compliance_config.json").write_text(
            cfg, encoding="utf-8")
        assert load_threshold(tmp_path) == 0


class TestDecide:
    def test_absent_summary_allows(self, tmp_path: Path):
        blocked, reason, details = decide(tmp_path)
        assert (blocked, reason, details) == (False, "", {})

    def test_clean_scan_allows(self, tmp_path: Path):
        _write(tmp_path, _summary())
        assert decide(tmp_path)[0] is False

    def test_unusable_blocks(self, tmp_path: Path):
        _write(tmp_path, None, raw="{oops")
        blocked, reason, details = decide(tmp_path)
        assert blocked is True
        assert "unreadable or malformed" in reason
        assert details["state"] == "unusable"
        assert details["summary_path"] == CI_SECURITY_REL

    def test_degraded_blocks_even_when_clean(self, tmp_path: Path):
        _write(tmp_path, _summary(degraded=True))
        blocked, reason, details = decide(tmp_path)
        assert blocked is True
        assert "degraded" in reason
        assert details["degraded"] is True

    def test_open_criticals_block_and_report_high_as_information(self, tmp_path: Path):
        _write(tmp_path, _summary(
            by_severity={"critical": 3, "high": 9, "medium": 0, "low": 0},
            critical_gate="fail"))
        blocked, reason, details = decide(tmp_path)
        assert blocked is True
        assert "3 open critical" in reason
        assert details["critical_findings"] == 3
        assert details["high_findings"] == 9          # informational only
        assert details["allowed_threshold"] == 0
        assert details["scan_date"] == "2026-07-28T07:51:37Z"

    def test_high_alone_does_not_block(self, tmp_path: Path):
        _write(tmp_path, _summary(
            by_severity={"critical": 0, "high": 9, "medium": 0, "low": 0},
            open_high_critical=9))
        assert decide(tmp_path)[0] is False

    def test_threshold_is_inclusive(self, tmp_path: Path):
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps({"enforcement": {"allowed_critical_findings": 2}}),
            encoding="utf-8")
        _write(tmp_path, _summary(by_severity={"critical": 2}, critical_gate="fail"))
        assert decide(tmp_path)[0] is False
        _write(tmp_path, _summary(by_severity={"critical": 3}, critical_gate="fail"))
        assert decide(tmp_path)[0] is True

    def test_gate_pass_without_counts_allows(self, tmp_path: Path):
        s = _summary(critical_gate="pass")
        del s["by_severity"]
        _write(tmp_path, s)
        assert decide(tmp_path)[0] is False

    def test_unsizeable_fail_blocks_at_every_threshold(self, tmp_path: Path):
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps({"enforcement": {"allowed_critical_findings": 99}}),
            encoding="utf-8")
        s = _summary(critical_gate="fail")
        del s["by_severity"]
        _write(tmp_path, s)
        blocked, reason, details = decide(tmp_path)
        assert blocked is True
        assert "cannot be sized" in reason
        assert details["state"] == "no-count"

    def test_no_verdict_at_all_blocks(self, tmp_path: Path):
        s = _summary(critical_gate="something-else")
        del s["by_severity"]
        _write(tmp_path, s)
        blocked, reason, details = decide(tmp_path)
        assert blocked is True
        assert details["state"] == "no-verdict"
