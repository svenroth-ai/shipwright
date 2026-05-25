"""Group H tests — Bloat-policy detective audit (Campaign A.review).

Findings: H1 Drift, H2 Ratchet-Suggest, H3 Anti-Ratchet, H4 Exception-no-ADR,
H5 Deferred-no-Plan, H6 Stale-Entry. H0 is the meta-finding (skip when
baseline absent, fail when malformed — see external-review #4).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_h  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_baseline(root: Path, entries: list[dict]) -> Path:
    path = root / "shipwright_bloat_baseline.json"
    path.write_text(
        json.dumps({"version": 1, "entries": entries}, indent=2),
        encoding="utf-8",
    )
    return path


def _write_py(root: Path, rel: str, n_lines: int) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    # ``n_lines`` newlines so ``read().count(b"\n") == n_lines``, matching
    # ``bloat_baseline._file_newlines`` semantics.
    p.write_text("x = 1\n" * n_lines, encoding="utf-8")
    return p


def _findings_by(findings, check_id: str):
    return [f for f in findings if f.check_id == check_id]


# ---------------------------------------------------------------------------
# H0 — baseline meta
# ---------------------------------------------------------------------------


def test_h0_skip_when_baseline_absent(tmp_path):
    findings = group_h.run(tmp_path, None, None)
    assert len(findings) == 1
    h0 = findings[0]
    assert h0.check_id == "H0"
    assert h0.status == "skip"
    assert h0.group == "H"


def test_h0_fail_when_baseline_malformed(tmp_path):
    # External-review #4: malformed (file exists, parse fails) MUST surface
    # as a fail finding, not be silently coalesced with the greenfield
    # "skip" branch — a corrupt baseline is real misconfiguration.
    bad = tmp_path / "shipwright_bloat_baseline.json"
    bad.write_text("{not json", encoding="utf-8")
    findings = group_h.run(tmp_path, None, None)
    assert any(f.check_id == "H0" and f.status == "fail" for f in findings), \
        f"expected H0 fail; got {[(f.check_id, f.status) for f in findings]}"


# ---------------------------------------------------------------------------
# H1 — Drift: oversize file NOT in baseline = hook bypass
# ---------------------------------------------------------------------------


def test_h1_flags_oversize_file_not_in_baseline(tmp_path):
    # File with 400 newlines exceeds the 300-LOC source limit and is NOT
    # listed in the baseline → H1 fail.
    _write_py(tmp_path, "src/big.py", 400)
    _write_baseline(tmp_path, entries=[])  # empty allowlist

    findings = group_h.run(tmp_path, None, None)
    h1 = _findings_by(findings, "H1")
    assert h1, f"expected H1 finding; got {[f.check_id for f in findings]}"
    assert h1[0].status == "fail"
    assert "src/big.py" in h1[0].detail or any(
        "src/big.py" in e for e in h1[0].evidence
    )


def test_h1_passes_when_oversize_file_is_grandfathered(tmp_path):
    _write_py(tmp_path, "src/big.py", 400)
    _write_baseline(tmp_path, entries=[{
        "path": "src/big.py", "limit": 300, "current": 400,
        "state": "grandfathered", "adr": None,
    }])

    findings = group_h.run(tmp_path, None, None)
    h1 = _findings_by(findings, "H1")
    assert h1
    assert h1[0].status == "pass"


def test_h1_fires_even_when_baseline_has_unrelated_states(tmp_path):
    # External-review OpenAI #1: H1 must fire on absent-from-baseline
    # regardless of other baseline entries' states.
    _write_py(tmp_path, "src/big.py", 400)
    _write_baseline(tmp_path, entries=[
        {"path": "src/other.py", "limit": 300, "current": 350,
         "state": "exception", "adr": ".shipwright/planning/adr/foo.md"},
    ])

    findings = group_h.run(tmp_path, None, None)
    h1 = _findings_by(findings, "H1")
    assert h1 and h1[0].status == "fail"


# ---------------------------------------------------------------------------
# H2 — Ratchet-Suggestion: baseline.current > actual file LOC
# ---------------------------------------------------------------------------


def test_h2_suggests_ratchet_when_file_shrank(tmp_path):
    # baseline says 500, file has only 380 newlines → H2 fail with
    # suggested current=380.
    _write_py(tmp_path, "src/foo.py", 380)
    _write_baseline(tmp_path, entries=[{
        "path": "src/foo.py", "limit": 300, "current": 500,
        "state": "grandfathered", "adr": None,
    }])

    findings = group_h.run(tmp_path, None, None)
    h2 = _findings_by(findings, "H2")
    assert h2, f"expected H2; got {[f.check_id for f in findings]}"
    assert h2[0].status == "fail"
    detail = h2[0].detail
    assert "src/foo.py" in detail
    assert "380" in detail


# ---------------------------------------------------------------------------
# H3 — Anti-Ratchet: state="anti-ratchet" is a committed bypass
# ---------------------------------------------------------------------------


def test_h3_flags_anti_ratchet_state(tmp_path):
    _write_py(tmp_path, "src/foo.py", 500)
    _write_baseline(tmp_path, entries=[{
        "path": "src/foo.py", "limit": 300, "current": 500,
        "state": "anti-ratchet", "adr": None,
    }])

    findings = group_h.run(tmp_path, None, None)
    h3 = _findings_by(findings, "H3")
    assert h3
    assert h3[0].status == "fail"
    assert h3[0].severity == "HIGH"
    assert "src/foo.py" in h3[0].detail


# ---------------------------------------------------------------------------
# H4 — Exception state requires ADR
# ---------------------------------------------------------------------------


def test_h4_flags_exception_without_adr(tmp_path):
    _write_py(tmp_path, "src/foo.py", 400)
    _write_baseline(tmp_path, entries=[{
        "path": "src/foo.py", "limit": 300, "current": 400,
        "state": "exception", "adr": None,
    }])

    findings = group_h.run(tmp_path, None, None)
    h4 = _findings_by(findings, "H4")
    assert h4 and h4[0].status == "fail"
    assert "src/foo.py" in h4[0].detail


# ---------------------------------------------------------------------------
# H5 — Deferred-plan state requires plan_ref
# ---------------------------------------------------------------------------


def test_h5_flags_deferred_plan_without_plan_ref(tmp_path):
    _write_py(tmp_path, "src/foo.py", 400)
    _write_baseline(tmp_path, entries=[{
        "path": "src/foo.py", "limit": 300, "current": 400,
        "state": "deferred-plan", "adr": None,
    }])

    findings = group_h.run(tmp_path, None, None)
    h5 = _findings_by(findings, "H5")
    assert h5 and h5[0].status == "fail"
    assert "src/foo.py" in h5[0].detail


# ---------------------------------------------------------------------------
# H6 — Stale-Entry: path missing on disk OR escapes project_root
# ---------------------------------------------------------------------------


def test_h6_flags_missing_file_in_baseline(tmp_path):
    # External-review Gemini #1 / OpenAI #5: a baseline entry whose path
    # no longer exists must NOT crash subsequent checks; instead surface
    # as H6 fail.
    _write_baseline(tmp_path, entries=[{
        "path": "src/deleted.py", "limit": 300, "current": 400,
        "state": "grandfathered", "adr": None,
    }])
    findings = group_h.run(tmp_path, None, None)
    h6 = _findings_by(findings, "H6")
    assert h6 and h6[0].status == "fail"
    assert "src/deleted.py" in h6[0].detail


def test_h6_flags_path_escaping_project_root(tmp_path):
    # External-review Gemini #5 / OpenAI #12: path-traversal guard.
    _write_baseline(tmp_path, entries=[{
        "path": "../escape.py", "limit": 300, "current": 400,
        "state": "grandfathered", "adr": None,
    }])
    findings = group_h.run(tmp_path, None, None)
    h6 = _findings_by(findings, "H6")
    assert h6 and h6[0].status == "fail"
    assert "escape" in h6[0].detail.lower()


# ---------------------------------------------------------------------------
# Composite pass-path + source-tag + group-letter parity
# (Consolidates per-finding "passes when X" tests to keep this file lean.)
# ---------------------------------------------------------------------------


def test_clean_baseline_passes_all_checks_and_tags_match(tmp_path):
    """One baseline that exercises the pass branch of every check class.

    Exception entry carries ADR; deferred-plan carries plan_ref; nothing
    is anti-ratchet; both files exist on disk and resolve under
    project_root; baseline lists every oversize file → H1 pass.
    """
    _write_py(tmp_path, "src/foo.py", 400)
    _write_py(tmp_path, "src/bar.py", 350)
    _write_py(tmp_path, "src/baz.py", 380)
    _write_baseline(tmp_path, entries=[
        {"path": "src/foo.py", "limit": 300, "current": 400,
         "state": "grandfathered", "adr": None},
        {"path": "src/bar.py", "limit": 300, "current": 350,
         "state": "exception",
         "adr": ".shipwright/planning/adr/099-bar.md"},
        {"path": "src/baz.py", "limit": 300, "current": 380,
         "state": "deferred-plan", "adr": None,
         "plan_ref": ".shipwright/planning/iterate/split-baz.md"},
    ])

    findings = group_h.run(tmp_path, None, None)
    # Every check class must have at least one pass; no fails.
    statuses = {f.check_id: f.status for f in findings}
    for cid in ("H1", "H2", "H3", "H4", "H5", "H6"):
        assert statuses.get(cid) == "pass", \
            f"{cid} not pass: {[(f.check_id, f.status) for f in findings]}"
    # Source / group parity on every finding.
    for f in findings:
        assert f.group == "H"
        assert f.source == SOURCE_DETECTIVE_ONLY


# ---------------------------------------------------------------------------
# Integration through real ``bloat_baseline.load()``
# (external-review OpenAI #10)
# ---------------------------------------------------------------------------


def test_integration_through_real_baseline_load(tmp_path):
    """External-review OpenAI #10: run() must read through real
    ``bloat_baseline.load()``, not an in-memory shortcut."""
    _write_py(tmp_path, "src/foo.py", 380)
    _write_baseline(tmp_path, entries=[{
        "path": "src/foo.py", "limit": 300, "current": 500,
        "state": "grandfathered", "adr": None,
    }])
    findings = group_h.run(tmp_path, None, None)
    h2 = _findings_by(findings, "H2")
    assert h2 and h2[0].status == "fail"
    assert "380" in h2[0].detail


# ---------------------------------------------------------------------------
# Registration: register_group("H", ...) succeeds (external-review #9)
# ---------------------------------------------------------------------------


def test_register_group_accepts_letter_h():
    from scripts.audit import audit_detector, _registry
    _registry.register_all()
    groups = audit_detector.registered_groups()
    assert "H" in groups, f"Group H not registered; got: {sorted(groups.keys())}"
    assert callable(groups["H"])
