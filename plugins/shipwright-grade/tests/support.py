"""Shared snapshot subject — one canonical :class:`ReportModel`.

Both the HTML and terminal snapshot goldens render FROM this single model so the
two golden files can never drift apart on the fixture. It carries a realistic
mix (ok / gap / n/a dimensions, a would-light funnel, top reasons) so the
snapshots exercise every section.
"""

from __future__ import annotations

from types import SimpleNamespace

from report_model import build_report_model

# Distinctive footer-timestamp tokens so a determinism test can null them out.
GEN_A = "GENSTAMP_AAAAA"
GEN_B = "GENSTAMP_BBBBB"

# Hostile payloads assembled via chr() so no literal control chars live here.
XSS = "<script>alert(1)</script>"
EVENT = '"><img src=x onerror=alert(1)>'
JS_URI = "javascript:alert(1)"
ANSI = "\x1b[31mRED\x1b[0m"
OSC8 = "\x1b]8;;https://evil.example\x07link\x1b]8;;\x07"
BIDI = chr(0x202E) + "evil" + chr(0x202C)
CTRL = "a\x07b\x00c"


def _dim(key, label, weight, score, anchor, detail):
    status = "n/a" if score is None else ("ok" if score >= 0.9 else "gap")
    return SimpleNamespace(key=key, label=label, weight=weight, score=score,
                           status=status, anchor=anchor, detail=detail)


def canonical_model():
    """A deterministic, section-complete model for snapshot tests."""
    dims = [
        _dim("requirement_traceability", "Requirement traceability", 0.25, 1.0,
             "requirement-to-work traceability (ISO/IEC/IEEE 29148)",
             "1/1 FRs covered; 2/2 changes traced (FR-linked or classified no-FR)"),
        _dim("test_health", "Test health", 0.20, None,
             "automated tests pass (OpenSSF Scorecard)",
             "3 test files across 1 framework (pytest) — present, not executed"),
        _dim("change_traceability", "Change traceability", 0.15, 0.5,
             "change provenance (SLSA)",
             "1/2 changes linked to a commit, ADR or test run"),
        _dim("change_reconciliation", "Change reconciliation", 0.15, None,
             "re-verify changed requirements (ISO/IEC/IEEE 12207)",
             "not measurable — needs per-change behavior-impact (BP-2)"),
        _dim("security", "Security", 0.10, None,
             "no open high/critical vulns (NIST SSDF)",
             "no code-scanning ingested (local-only)"),
        _dim("maintainability", "Size / maintainability discipline", 0.10, 0.85,
             "bounded module size (ISO/IEC 25010)",
             "2/13 source files over 300 LOC"),
        _dim("dependency_hygiene", "Dependency hygiene", 0.05, None,
             "dependency license & risk (OWASP)", "no dependency manifest"),
    ]
    report = SimpleNamespace(
        grade="B", score=82.5, gradeable=True,
        verdict="Controlled, minor gaps. Primarily capped by change traceability.",
        band_label="Controlled, minor gaps.", dimensions=dims,
        reasons=["Change traceability: 1/2 changes linked to a commit, ADR or test run"],
        verified_from="shipwright-grade heuristic @ deadbeefcafe1234 (local-only)",
    )
    routing = SimpleNamespace(effective_mode="heuristic", state="absent",
                              reason="no .shipwright/ directory")
    return build_report_model(
        grade_report=report, routing=routing, target_display="sample-repo",
        head_sha="deadbeefcafe1234", events_truncated=False,
        static_test_inventory=(
            "3 test files across 1 framework (pytest) — present, not executed; "
            "CI workflow present"),
        network_note="local-only (default) — pass --allow-network to enrich via GitHub",
    )


def dim(key, label, weight, score, *, anchor="std anchor", detail="d"):
    """A single :class:`DimensionResult`-shaped namespace for ad-hoc models."""
    return _dim(key, label, weight, score, anchor, detail)


def mixed_dims(*, hostile=False):
    """7 dimensions (ok / gap / n/a mix); ``hostile`` injects XSS/ANSI/bidi."""
    rt_detail = "1/1 FRs covered; 2/2 changes traced"
    ct_detail = "1/2 changes linked to a commit, ADR or test run"
    if hostile:
        rt_detail = f"1/1 {XSS} covered {ANSI}{BIDI}"
        ct_detail = f"{EVENT} {JS_URI} {OSC8}{CTRL}"
    return [
        _dim("requirement_traceability", "Requirement traceability", 0.25, 1.0,
             "requirement-to-work traceability (ISO/IEC/IEEE 29148)", rt_detail),
        _dim("test_health", "Test health", 0.20, None,
             "automated tests pass (OpenSSF Scorecard)",
             "3 test files across 1 framework — present, not executed"),
        _dim("change_traceability", "Change traceability", 0.15, 0.5,
             "change provenance (SLSA)", ct_detail),
        _dim("change_reconciliation", "Change reconciliation", 0.15, None,
             "re-verify changed requirements (ISO/IEC/IEEE 12207)",
             "not measurable — needs per-change behavior-impact (BP-2)"),
        _dim("security", "Security", 0.10, None,
             "no open high/critical vulns (NIST SSDF)",
             "no code-scanning ingested (local-only)"),
        _dim("maintainability", "Size / maintainability discipline", 0.10, 0.85,
             "bounded module size (ISO/IEC 25010)",
             "2/13 source files over 300 LOC"),
        _dim("dependency_hygiene", "Dependency hygiene", 0.05, None,
             "dependency license & risk (OWASP)", "no dependency manifest"),
    ]


def mixed_model(*, hostile=False, **net):
    """The section-complete model used by the non-snapshot HTML tests."""
    target = "sample-repo" if not hostile else f"sample{XSS}{ANSI}{BIDI}"
    reasons = ["Change traceability: 1/2 changes linked to a commit, ADR or test run"]
    if hostile:
        reasons = [f"Change traceability: {XSS} {EVENT}"]
    report = SimpleNamespace(
        grade="B", score=82.5, gradeable=True,
        verdict="Controlled, minor gaps. Primarily capped by change traceability.",
        band_label="Controlled, minor gaps.", dimensions=mixed_dims(hostile=hostile),
        reasons=reasons, verified_from="shipwright-grade heuristic @ deadbeefcafe1234")
    routing = SimpleNamespace(effective_mode="heuristic", state="absent",
                              reason="no .shipwright/ directory")
    return build_report_model(
        grade_report=report, routing=routing, target_display=target,
        head_sha="deadbeefcafe1234", events_truncated=False,
        static_test_inventory="3 test files across 1 framework — present, not executed",
        **net)
