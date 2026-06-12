"""Tests for the shared architecture-doc reconciliation helper.

Single source of truth shared by the compliance Group F detective (F5) and the
iterate F11 finalize gate (``check_architecture_documented``). Keeping the
matching rule + impact vocabulary in one place is what stops the detective and
the finalizer from drifting apart (external-review #2/#4,
iterate-2026-06-06-arch-drift-detector).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

from lib.architecture_doc import (  # noqa: E402
    IMPACT_TARGETS,
    NULL_IMPACTS,
    REAL_IMPACTS,
    corrupt_for_run,
    impact_documented,
    missing_entries,
    normalize_impact,
    records_for_run,
    run_id_documented,
    scan_drops,
    target_for_impact,
    unknown_impact_records,
)


def _write_drop(drops: Path, run_id: str, impact: str, *, suffix: str = "_001") -> None:
    drops.mkdir(parents=True, exist_ok=True)
    (drops / f"{run_id}{suffix}.json").write_text(
        json.dumps({"run_id": run_id, "architecture_impact": impact}),
        encoding="utf-8",
    )


# --- vocabulary -------------------------------------------------------------


def test_impact_vocabulary():
    assert REAL_IMPACTS == frozenset({"component", "data-flow", "convention"})
    assert "none" in NULL_IMPACTS and "" in NULL_IMPACTS


def test_normalize_impact_case_and_type():
    assert normalize_impact("  Convention ") == "convention"
    assert normalize_impact("DATA-FLOW") == "data-flow"
    assert normalize_impact(None) == ""
    assert normalize_impact(123) == ""


# --- IMPACT_TARGETS routing SSoT --------------------------------------------


def test_impact_targets_cover_real_impacts():
    assert set(IMPACT_TARGETS) == REAL_IMPACTS


def test_impact_targets_route_convention_to_conventions_doc():
    assert IMPACT_TARGETS["convention"] == ("conventions.md", "## Convention Updates")
    assert IMPACT_TARGETS["component"] == ("architecture.md", "## Architecture Updates")
    assert IMPACT_TARGETS["data-flow"] == ("architecture.md", "## Architecture Updates")


def test_target_for_impact_normalizes_and_rejects():
    assert target_for_impact("  Convention ") == ("conventions.md", "## Convention Updates")
    assert target_for_impact("none") is None
    assert target_for_impact("frobnicate") is None
    assert target_for_impact(None) is None


# --- impact_documented: routing per IMPACT_TARGETS --------------------------


def test_impact_documented_convention_in_conventions_doc():
    texts = {"conventions.md": "- iter-conv (convention): x", "architecture.md": ""}
    assert impact_documented("convention", "iter-conv", texts)


def test_impact_documented_convention_only_in_architecture_is_not_documented():
    # The legacy convention -> architecture.md fallback was RETIRED
    # (iterate-2026-06-12-compress-agent-doc-backlog): a convention run_id found
    # only in architecture.md no longer counts — it MUST live in conventions.md.
    texts = {"conventions.md": "", "architecture.md": "- iter-conv (convention): x"}
    assert not impact_documented("convention", "iter-conv", texts)


def test_impact_documented_component_not_satisfied_by_conventions_doc():
    # component/data-flow have NO conventions.md fallback — only architecture.md.
    texts = {"conventions.md": "- iter-comp (component): x", "architecture.md": ""}
    assert not impact_documented("component", "iter-comp", texts)


# --- missing_entries: impact-aware routing ----------------------------------


def test_missing_entries_convention_routes_to_conventions_doc(tmp_path: Path):
    drops = tmp_path / "decision-drops"
    _write_drop(drops, "iter-conv", "convention")
    _write_drop(drops, "iter-comp", "component")
    records, _ = scan_drops(drops)
    # convention documented in conventions.md; component in architecture.md.
    texts = {
        "conventions.md": "- iter-conv (convention): documented",
        "architecture.md": "- iter-comp (component): documented",
    }
    assert missing_entries(records, texts) == []


def test_missing_entries_convention_only_in_arch_doc_is_missing(tmp_path: Path):
    # Post-retirement: a convention drop documented only in architecture.md is NOT
    # satisfied — it must be migrated to conventions.md ## Convention Updates.
    drops = tmp_path / "decision-drops"
    _write_drop(drops, "iter-conv", "convention")
    records, _ = scan_drops(drops)
    texts = {"conventions.md": "", "architecture.md": "- iter-conv (convention): legacy"}
    assert {r.run_id for r in missing_entries(records, texts)} == {"iter-conv"}


def test_missing_entries_component_in_conventions_doc_is_missing(tmp_path: Path):
    drops = tmp_path / "decision-drops"
    _write_drop(drops, "iter-comp", "component")
    records, _ = scan_drops(drops)
    # component documented in the WRONG doc (conventions.md) → still missing.
    texts = {"conventions.md": "- iter-comp (component): wrong-doc", "architecture.md": ""}
    assert {r.run_id for r in missing_entries(records, texts)} == {"iter-comp"}


# --- run_id_documented: word-boundary match ---------------------------------


def test_run_id_documented_present():
    assert run_id_documented("- iterate-2026-06-06-foo (component): x", "iterate-2026-06-06-foo")


def test_run_id_documented_absent():
    assert not run_id_documented("nothing here", "iterate-2026-06-06-foo")


def test_run_id_documented_prefix_collision_rejected():
    # A documented longer run_id must NOT satisfy a shorter prefix run_id.
    text = "- iterate-2026-06-06-foo-extended (component): x"
    assert not run_id_documented(text, "iterate-2026-06-06-foo")


def test_run_id_documented_empty_is_false():
    assert not run_id_documented("anything", "")


# --- scan_drops -------------------------------------------------------------


def test_scan_drops_parses_and_normalizes(tmp_path: Path):
    drops = tmp_path / "decision-drops"
    _write_drop(drops, "iter-a", "Component")  # title-case → normalized
    _write_drop(drops, "iter-b", "none")
    records, corrupt = scan_drops(drops)
    assert corrupt == []
    by_run = {r.run_id: r.impact for r in records}
    assert by_run == {"iter-a": "component", "iter-b": "none"}


def test_scan_drops_collects_corrupt(tmp_path: Path):
    drops = tmp_path / "decision-drops"
    drops.mkdir(parents=True)
    (drops / "broken_001.json").write_text("{ not json", encoding="utf-8")
    records, corrupt = scan_drops(drops)
    assert records == []
    assert corrupt == ["broken_001.json"]


def test_scan_drops_absent_dir(tmp_path: Path):
    records, corrupt = scan_drops(tmp_path / "nope")
    assert records == [] and corrupt == []


# --- missing_entries --------------------------------------------------------


def test_missing_entries_flags_undocumented_arch_impact(tmp_path: Path):
    drops = tmp_path / "decision-drops"
    _write_drop(drops, "iter-comp", "component")
    _write_drop(drops, "iter-conv", "convention")  # convention IS arch-impact
    _write_drop(drops, "iter-none", "none")  # not arch-impact → ignored
    records, _ = scan_drops(drops)
    arch_text = "- iter-comp (component): documented\n"  # only iter-comp present
    missing = missing_entries(records, arch_text)
    assert {r.run_id for r in missing} == {"iter-conv"}


def test_missing_entries_all_documented(tmp_path: Path):
    drops = tmp_path / "decision-drops"
    _write_drop(drops, "iter-comp", "component")
    records, _ = scan_drops(drops)
    arch_text = "- iter-comp (component): documented\n"
    assert missing_entries(records, arch_text) == []


# --- unknown impact (defensive) ---------------------------------------------


def test_unknown_impact_records_surfaced(tmp_path: Path):
    drops = tmp_path / "decision-drops"
    _write_drop(drops, "iter-weird", "frobnicate")
    _write_drop(drops, "iter-ok", "component")
    _write_drop(drops, "iter-none", "none")
    records, _ = scan_drops(drops)
    unknown = unknown_impact_records(records)
    assert {r.run_id for r in unknown} == {"iter-weird"}


# --- per-run lookups (F11 gate) ---------------------------------------------


def test_records_for_run_exact_match(tmp_path: Path):
    drops = tmp_path / "decision-drops"
    _write_drop(drops, "iter-c1", "convention")
    _write_drop(drops, "iter-c1-gitignore", "convention")
    records, _ = scan_drops(drops)
    got = records_for_run(records, "iter-c1")
    assert {r.run_id for r in got} == {"iter-c1"}  # not the longer one


def test_corrupt_for_run_matches_by_filename(tmp_path: Path):
    drops = tmp_path / "decision-drops"
    drops.mkdir(parents=True)
    (drops / "iter-x_001.json").write_text("{ broken", encoding="utf-8")
    (drops / "iter-y_001.json").write_text("{ broken", encoding="utf-8")
    _, corrupt = scan_drops(drops)
    assert corrupt_for_run(corrupt, "iter-x") == ["iter-x_001.json"]
    assert corrupt_for_run(corrupt, "iter-z") == []
