"""Groups C + F preventive-rerun tests (plan v7, Step 6).

Both groups are pure import orchestration over iterate-12 check
functions. These tests cover the adapter layer: every check in the
group emits exactly one Finding with source='preventive-rerun', and
one imported check crashing does not drop the others.
"""

from __future__ import annotations

import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_c, group_f  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_PREVENTIVE_RERUN  # noqa: E402


class _FakeCheck:
    def __init__(self, name, ok, severity="error", detail=""):
        self.name = name
        self.ok = ok
        self.severity = severity
        self.detail = detail


def _patch_iterate12(monkeypatch, module, mapping):
    """Swap ``import_iterate12_checks`` on the target module."""
    def _fake():
        return mapping
    monkeypatch.setattr(module, "import_iterate12_checks", _fake)


def _passing_checks(ids):
    return {cid: (lambda _r, cid=cid: _FakeCheck(cid, ok=True)) for cid in ids}


# ---------------------------------------------------------------------------
# Group C
# ---------------------------------------------------------------------------


_GROUP_C_IDS = [
    "check_design_fr_coverage",
    "check_fr_orphans_in_plan",
    "check_section_files_match_manifest",
    "check_section_id_validity",
]


def test_group_c_emits_finding_per_check(monkeypatch, tmp_path):
    _patch_iterate12(monkeypatch, group_c, _passing_checks(_GROUP_C_IDS))
    findings = group_c.run(tmp_path, None, None)
    assert len(findings) == 4
    assert {f.check_id for f in findings} == {"C1", "C2", "C3", "C4"}
    for f in findings:
        assert f.group == "C"
        assert f.source == SOURCE_PREVENTIVE_RERUN
        assert f.status == "pass"


def test_group_c_surfaces_check_failures(monkeypatch, tmp_path):
    mapping = _passing_checks(_GROUP_C_IDS)
    mapping["check_fr_orphans_in_plan"] = lambda _r: _FakeCheck(
        "check_fr_orphans_in_plan", ok=False, detail="orphan FR-05.02",
    )
    _patch_iterate12(monkeypatch, group_c, mapping)
    findings = group_c.run(tmp_path, None, None)
    c2 = next(f for f in findings if f.check_id == "C2")
    assert c2.status == "fail"
    assert "orphan FR-05.02" in c2.detail
    assert c2.suggested_iterate_cmd  # non-empty, contains copy-pasteable hint
    # Suggestion must reference the check_id and the audit report path so
    # /shipwright-iterate has a pointer back to the findings.
    assert "C2" in c2.suggested_iterate_cmd
    assert "compliance/audit-report.md" in c2.suggested_iterate_cmd


def test_group_c_isolates_check_crashes(monkeypatch, tmp_path):
    mapping = _passing_checks(_GROUP_C_IDS)

    def boom(_r):
        raise RuntimeError("verifier exploded")
    mapping["check_design_fr_coverage"] = boom
    _patch_iterate12(monkeypatch, group_c, mapping)

    findings = group_c.run(tmp_path, None, None)
    assert len(findings) == 4  # all 4 present
    c1 = next(f for f in findings if f.check_id == "C1")
    assert c1.status == "fail"
    assert "RuntimeError" in c1.detail
    # Remaining checks still pass
    assert all(f.status == "pass" for f in findings if f.check_id != "C1")


def test_group_c_maps_skipped_checks(monkeypatch, tmp_path):
    mapping = _passing_checks(_GROUP_C_IDS)
    mapping["check_section_id_validity"] = lambda _r: _FakeCheck(
        "check_section_id_validity", ok=None, severity="skipped",
        detail="no plan.md found",
    )
    _patch_iterate12(monkeypatch, group_c, mapping)
    findings = group_c.run(tmp_path, None, None)
    c4 = next(f for f in findings if f.check_id == "C4")
    assert c4.status == "skip"


# ---------------------------------------------------------------------------
# Group F
# ---------------------------------------------------------------------------


_GROUP_F_IDS = [
    "check_adr_ids_sequential",
    "check_adr_status_valid",
    "check_adr_supersession_exists",
]


def test_group_f_emits_finding_per_check(monkeypatch, tmp_path):
    _patch_iterate12(monkeypatch, group_f, _passing_checks(_GROUP_F_IDS))
    findings = group_f.run(tmp_path, None, None)
    # Iterate C.2 (ADR-060) added F4-F7 detective-only doc-hygiene
    # checks alongside F1-F3 preventive-rerun structural checks.
    assert len(findings) == 7
    assert {f.check_id for f in findings} == {"F1", "F2", "F3", "F4", "F5", "F6", "F7"}
    for f in findings:
        assert f.group == "F"
    f_legacy = [f for f in findings if f.check_id in {"F1", "F2", "F3"}]
    assert all(f.source == SOURCE_PREVENTIVE_RERUN for f in f_legacy)
    f_new = [f for f in findings if f.check_id in {"F4", "F5", "F6", "F7"}]
    from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY
    assert all(f.source == SOURCE_DETECTIVE_ONLY for f in f_new)


def test_group_f_detects_gap_in_ids(monkeypatch, tmp_path):
    mapping = _passing_checks(_GROUP_F_IDS)
    mapping["check_adr_ids_sequential"] = lambda _r: _FakeCheck(
        "check_adr_ids_sequential", ok=False,
        detail="gap between ADR-003 and ADR-005",
    )
    _patch_iterate12(monkeypatch, group_f, mapping)
    findings = group_f.run(tmp_path, None, None)
    f1 = next(f for f in findings if f.check_id == "F1")
    assert f1.status == "fail"
    assert "gap" in f1.detail


# ---------------------------------------------------------------------------
# End-to-end through the detector + registry
# ---------------------------------------------------------------------------


def test_registry_wires_c_and_f(monkeypatch, tmp_path):
    from scripts.audit import audit_detector
    from scripts.audit._registry import register_all

    # Stub out both iterate-12 lookups so the test is hermetic.
    _patch_iterate12(monkeypatch, group_c, _passing_checks(_GROUP_C_IDS))
    _patch_iterate12(monkeypatch, group_f, _passing_checks(_GROUP_F_IDS))

    register_all()

    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")
    report = audit_detector.run_all(tmp_path, run_gate=False)

    ids = {f.check_id for f in report.findings}
    assert {"C1", "C2", "C3", "C4", "F1", "F2", "F3"}.issubset(ids)
    # Sub-Iterate C wired Groups E + G, so no group should fall through
    # to "not-implemented" any more.
    skipped_groups = {g for g, _r in report.groups_skipped}
    assert skipped_groups == set()


# ---------------------------------------------------------------------------
# Iterate C.2 (ADR-060) — F4-F7 detective-only documentation hygiene
# ---------------------------------------------------------------------------


import json
from pathlib import Path


def _seed_decision_log(root: Path, sections: list[tuple[str, int, bool]]) -> None:
    """Write a synthetic decision_log.md.

    ``sections``: list of ``(adr_id, body_line_count, include_spec_ref)``.
    """
    doc = root / ".shipwright" / "agent_docs"
    doc.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# Decision Log", ""]
    for adr_id, body_lines, include_ref in sections:
        n = int(adr_id.split("-")[1])
        lines.append(f"### ADR-{n:03d}: Test ADR {n}")
        if include_ref:
            # Mirrors the aggregate_decisions.py render shape verbatim
            # (which uses relative paths `../planning/adr/...` from the
            # 2-deep decision_log.md). artifact-path-canon: legacy
            lines.append("- **Details:** [planning/adr/...](../planning/adr/000-x.md)")  # artifact-path-canon: legacy
            body_lines = max(0, body_lines - 1)
        for i in range(body_lines):
            lines.append(f"line {i}")
        lines.append("")
    (doc / "decision_log.md").write_text("\n".join(lines), encoding="utf-8")


def _seed_arch_drop(root: Path, name: str, *, impact: str) -> None:
    drops = root / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True, exist_ok=True)
    (drops / name).write_text(
        json.dumps({"run_id": name.replace(".json", ""), "architecture_impact": impact}),
        encoding="utf-8",
    )


class TestF4AdrBloat:
    def test_no_bloated_adrs_passes(self, tmp_path: Path):
        _seed_decision_log(tmp_path, [
            ("ADR-001", 30, False),
            ("ADR-002", 50, False),
        ])
        findings = group_f.run(tmp_path, None, None)
        f4 = next(f for f in findings if f.check_id == "F4")
        assert f4.status == "pass"

    def test_bloated_adr_without_spec_ref_fails(self, tmp_path: Path):
        _seed_decision_log(tmp_path, [
            ("ADR-001", 30, False),
            ("ADR-002", 80, False),  # bloated
        ])
        findings = group_f.run(tmp_path, None, None)
        f4 = next(f for f in findings if f.check_id == "F4")
        assert f4.status == "fail"
        assert "ADR-002" in f4.detail

    def test_bloated_adr_with_spec_ref_passes(self, tmp_path: Path):
        _seed_decision_log(tmp_path, [
            ("ADR-001", 90, True),  # bloated but linked to spec
        ])
        findings = group_f.run(tmp_path, None, None)
        f4 = next(f for f in findings if f.check_id == "F4")
        assert f4.status == "pass"

    def test_missing_decision_log_skips(self, tmp_path: Path):
        # No decision_log.md, no drops, no CLAUDE.md.
        findings = group_f.run(tmp_path, None, None)
        f4 = next(f for f in findings if f.check_id == "F4")
        assert f4.status == "skip"


class TestF5ArchDrift:
    """Content-oracle F5: each arch-impact drop's run_id must appear in
    architecture.md (iterate-2026-06-06-arch-drift-detector). Replaces the
    prior marker/git-log oracle, which never fired on gitignored drops."""

    @staticmethod
    def _seed_arch_md(root: Path, text: str) -> None:
        doc = root / ".shipwright" / "agent_docs"
        doc.mkdir(parents=True, exist_ok=True)
        (doc / "architecture.md").write_text(text, encoding="utf-8")

    @staticmethod
    def _seed_conv_md(root: Path, text: str) -> None:
        doc = root / ".shipwright" / "agent_docs"
        doc.mkdir(parents=True, exist_ok=True)
        (doc / "conventions.md").write_text(text, encoding="utf-8")

    def test_absent_drops_dir_skips(self, tmp_path: Path):
        # No decision-drops dir at all (clean checkout / CI) → skip, not fail.
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "skip"

    def test_empty_drops_dir_passes(self, tmp_path: Path):
        (tmp_path / ".shipwright" / "agent_docs" / "decision-drops").mkdir(parents=True)
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "pass"

    def test_undocumented_component_drop_fails(self, tmp_path: Path):
        _seed_arch_drop(tmp_path, "iter-001_001.json", impact="component")
        self._seed_arch_md(tmp_path, "# Architecture\n\n## Architecture Updates\n")
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "fail"
        assert "not documented" in f5.detail
        assert "iter-001_001" in str(f5.evidence)

    def test_documented_component_drop_passes(self, tmp_path: Path):
        _seed_arch_drop(tmp_path, "iter-001_001.json", impact="component")
        self._seed_arch_md(
            tmp_path,
            "## Architecture Updates\n- iter-001_001 (component): documented.\n",
        )
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "pass"

    def test_convention_impact_now_counted(self, tmp_path: Path):
        # Regression: the old F5 ignored `convention`; the new F5 reconciles it.
        _seed_arch_drop(tmp_path, "iter-conv_001.json", impact="convention")
        self._seed_arch_md(tmp_path, "## Architecture Updates\n")  # undocumented
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "fail"
        assert "iter-conv_001" in str(f5.evidence)

    def test_convention_documented_in_conventions_doc_passes(self, tmp_path: Path):
        # Canonical route: a convention run_id in conventions.md ## Convention
        # Updates satisfies F5 even with an empty architecture.md.
        _seed_arch_drop(tmp_path, "iter-conv_001.json", impact="convention")
        self._seed_arch_md(tmp_path, "## Architecture Updates\n")
        self._seed_conv_md(
            tmp_path,
            "## Convention Updates\n- **ADR-001** (2026-06-12): iter-conv_001 — x\n",
        )
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "pass"

    def test_convention_only_in_architecture_fails_post_retirement(self, tmp_path: Path):
        # Fallback retired (iterate-2026-06-12-compress-agent-doc-backlog): a convention
        # run_id only in architecture.md no longer satisfies F5 (must be conventions.md).
        _seed_arch_drop(tmp_path, "iter-conv_001.json", impact="convention")
        self._seed_arch_md(
            tmp_path, "## Architecture Updates\n- iter-conv_001 (convention): legacy\n"
        )
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "fail"

    def test_data_flow_impact_caught(self, tmp_path: Path):
        _seed_arch_drop(tmp_path, "iter-df_001.json", impact="data-flow")
        self._seed_arch_md(tmp_path, "## Architecture Updates\n")
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "fail"

    def test_none_impact_ignored(self, tmp_path: Path):
        _seed_arch_drop(tmp_path, "iter-none_001.json", impact="none")
        self._seed_arch_md(tmp_path, "## Architecture Updates\n")
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "pass"

    def test_arch_md_missing_with_arch_drops_fails(self, tmp_path: Path):
        # component drop exists but its target doc (architecture.md) is absent →
        # the run_id reads as undocumented and F5 fails (no silent pass).
        _seed_arch_drop(tmp_path, "iter-001_001.json", impact="component")
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "fail"
        assert "not documented" in f5.detail
        assert "iter-001_001" in str(f5.evidence)

    def test_unknown_impact_surfaced(self, tmp_path: Path):
        _seed_arch_drop(tmp_path, "iter-weird_001.json", impact="frobnicate")
        self._seed_arch_md(tmp_path, "## Architecture Updates\n")
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "fail"
        assert "unrecognized" in f5.detail


class TestF6F7ClaudeMdHygiene:
    def test_no_claude_md_skips(self, tmp_path: Path):
        findings = group_f.run(tmp_path, None, None)
        f6 = next(f for f in findings if f.check_id == "F6")
        f7 = next(f for f in findings if f.check_id == "F7")
        assert f6.status == "skip"
        assert f7.status == "skip"

    def test_small_claude_md_passes(self, tmp_path: Path):
        (tmp_path / "CLAUDE.md").write_text(
            "\n".join(f"line {i}" for i in range(50)),
            encoding="utf-8",
        )
        findings = group_f.run(tmp_path, None, None)
        f6 = next(f for f in findings if f.check_id == "F6")
        assert f6.status == "pass"

    def test_oversized_claude_md_fails_f6(self, tmp_path: Path):
        (tmp_path / "CLAUDE.md").write_text(
            "\n".join(f"line {i}" for i in range(250)),
            encoding="utf-8",
        )
        findings = group_f.run(tmp_path, None, None)
        f6 = next(f for f in findings if f.check_id == "F6")
        assert f6.status == "fail"
        assert "250" in f6.detail

    def test_iterate_annotation_leak_fails_f7(self, tmp_path: Path):
        content = (
            "# CLAUDE.md\n"
            "## Architecture\n"
            "Iterate A.1 (ADR-048) — Mermaid architecture.\n"
            "Iterate A.3 (ADR-049) — ADR hard-reject.\n"
            "Iterate B.1 (ADR-055) — dashboard mode-aware.\n"
            "Iterate B0 (ADR-054) — triage producer contract.\n"
            "Iterate B.2 (ADR-056) — SBOM polish.\n"
            "Iterate B.3 (ADR-057) — test-evidence.\n"
        )
        (tmp_path / "CLAUDE.md").write_text(content, encoding="utf-8")
        findings = group_f.run(tmp_path, None, None)
        f7 = next(f for f in findings if f.check_id == "F7")
        assert f7.status == "fail"
        # The detail should mention how many references were found.
        assert "6" in f7.detail or "exceeds" in f7.detail

    def test_few_iterate_annotations_passes_f7(self, tmp_path: Path):
        content = (
            "# CLAUDE.md\n"
            "Brief: Iterate A.1 introduced X. Iterate B.2 introduced Y.\n"
        )
        (tmp_path / "CLAUDE.md").write_text(content, encoding="utf-8")
        findings = group_f.run(tmp_path, None, None)
        f7 = next(f for f in findings if f.check_id == "F7")
        assert f7.status == "pass"


class TestF4Ordering:
    """Code-review-M4: heaviest-5 sorted descending, evidence carries full list."""

    def test_top5_ordering_and_full_evidence(self, tmp_path: Path):
        # 6 bloated ADRs with varying line counts (none with spec_ref).
        sizes = [(1, 70), (2, 90), (3, 100), (4, 75), (5, 85), (6, 65)]
        sections = [(f"ADR-{n:03d}", size, False) for n, size in sizes]
        _seed_decision_log(tmp_path, sections)
        findings = group_f.run(tmp_path, None, None)
        f4 = next(f for f in findings if f.check_id == "F4")
        assert f4.status == "fail"
        # Top-5 in detail: by size desc, ADR-003 (100), ADR-002 (90),
        # ADR-005 (85), ADR-004 (75), ADR-001 (70). ADR-006 (65) is
        # the 6th, mentioned via "(+1)".
        detail = f4.detail
        # Order in detail must match descending line count.
        idx_003 = detail.index("ADR-003")
        idx_002 = detail.index("ADR-002")
        idx_005 = detail.index("ADR-005")
        idx_004 = detail.index("ADR-004")
        idx_001 = detail.index("ADR-001")
        assert idx_003 < idx_002 < idx_005 < idx_004 < idx_001
        assert "(+1)" in detail  # 6 - 5 = 1 more
        # Evidence carries ALL 6 entries (full list).
        assert len(f4.evidence) == 6
        evidence_ids = [e.split(":")[0] for e in f4.evidence]
        assert set(evidence_ids) == {f"ADR-{n:03d}" for n in range(1, 7)}


class TestF7RegexVariants:
    """Code-review-M3: regex matches the spec's canonical forms."""

    def _seed_claude(self, root: Path, body: str) -> None:
        (root / "CLAUDE.md").write_text(body, encoding="utf-8")

    def test_iterate_with_dot_id_and_adr_ref(self, tmp_path: Path):
        # "Iterate A.1 (ADR-048)" — explicit form.
        self._seed_claude(
            tmp_path,
            "Iterate A.1 (ADR-048) — x\n" * 6,
        )
        findings = group_f.run(tmp_path, None, None)
        f7 = next(f for f in findings if f.check_id == "F7")
        assert f7.status == "fail"

    def test_iterate_bare_id_no_adr(self, tmp_path: Path):
        # "Iterate B0" — bare form without ADR reference.
        self._seed_claude(
            tmp_path,
            "Iterate B0 — y\n" * 6,
        )
        findings = group_f.run(tmp_path, None, None)
        f7 = next(f for f in findings if f.check_id == "F7")
        assert f7.status == "fail"

    def test_iterate_with_em_dash_and_label(self, tmp_path: Path):
        # "Iterate B.2 — SBOM polish" — prose form with em-dash.
        self._seed_claude(
            tmp_path,
            "Iterate B.2 — SBOM polish\n" * 6,
        )
        findings = group_f.run(tmp_path, None, None)
        f7 = next(f for f in findings if f.check_id == "F7")
        assert f7.status == "fail"

    def test_evidence_carries_all_matches_not_just_first_three(self, tmp_path: Path):
        body = "\n".join(f"Iterate B.{i} — desc" for i in range(7))
        self._seed_claude(tmp_path, body)
        findings = group_f.run(tmp_path, None, None)
        f7 = next(f for f in findings if f.check_id == "F7")
        assert f7.status == "fail"
        # All 7 matches in evidence (not just the top-3 sample shown in detail).
        assert len(f7.evidence) == 7


class TestF4SpecRefShapeCheck:
    """Reviewer-flagged OpenAI-M1 — only the canonical link counts as spec_ref."""

    def test_bare_details_text_without_link_does_not_pass(self, tmp_path: Path):
        # Bloated ADR + body mentions "Details" verbatim but as plain
        # text, not as a `**Details:** [...](url)` link → still bloated.
        doc = tmp_path / ".shipwright" / "agent_docs"
        doc.mkdir(parents=True)
        body_text = "\n".join(f"line {i}" for i in range(80))
        # Mention "Details" in body but NOT as a real link.
        body_text = "More Details follow:\n" + body_text
        (doc / "decision_log.md").write_text(
            "# Decision Log\n\n### ADR-001: Test\n" + body_text + "\n",
            encoding="utf-8",
        )
        findings = group_f.run(tmp_path, None, None)
        f4 = next(f for f in findings if f.check_id == "F4")
        assert f4.status == "fail"

    def test_real_details_link_passes(self, tmp_path: Path):
        doc = tmp_path / ".shipwright" / "agent_docs"
        doc.mkdir(parents=True)
        body_text = "- **Details:** [planning/adr/001-spec.md](../planning/adr/001-spec.md)\n"  # artifact-path-canon: legacy
        body_text += "\n".join(f"line {i}" for i in range(80))
        (doc / "decision_log.md").write_text(
            "# Decision Log\n\n### ADR-001: Test\n" + body_text + "\n",
            encoding="utf-8",
        )
        findings = group_f.run(tmp_path, None, None)
        f4 = next(f for f in findings if f.check_id == "F4")
        assert f4.status == "pass"


class TestF5CorruptDrops:
    """A malformed drop must surface as a fail, never silently hide drift
    (preserved from the prior F5; the marker-SHA hardening tests are retired
    with the git-log oracle — iterate-2026-06-06-arch-drift-detector)."""

    def test_corrupt_drop_file_surfaces_as_fail(self, tmp_path: Path):
        drops = tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
        drops.mkdir(parents=True)
        (drops / "broken.json").write_text("{ not valid json", encoding="utf-8")
        findings = group_f.run(tmp_path, None, None)
        f5 = next(f for f in findings if f.check_id == "F5")
        assert f5.status == "fail"
        assert "failed to parse" in f5.detail
        assert "broken.json" in f5.detail
