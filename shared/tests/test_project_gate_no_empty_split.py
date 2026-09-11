"""Tests for ``check_no_empty_split`` and ``_is_safe_split_name`` in
``shared/scripts/tools/verifiers/_project_gate_wiring.py``.

Split out of ``test_verifiers_project.py`` (shared bloat gate, 300-line
limit; req3-06-enforcement-mono sub-iterate e2) — ``check_no_empty_split``
carries the largest share of this module's external-review regression
tests (manifest parsing, split-name safety, missing/unreadable specs), so
it gets its own file. ``check_basis_forbids_assumed``,
``check_criteria_free_of_implementation_detail`` and
``check_starting_guidance_present`` live in
``test_project_gate_basis_and_guidance.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.verifiers._project_gate_wiring import (  # noqa: E402
    _is_safe_split_name,
    check_no_empty_split,
)

from _project_check_fixtures import _write_splits_config  # noqa: E402


def test_check_no_empty_split_fails_when_a_split_has_zero_fr_rows(tmp_path):
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text("# spec\n\nNothing here yet.\n", encoding="utf-8")
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "01-a" in r.detail


def test_check_no_empty_split_fails_loud_when_names_are_all_null_or_empty(tmp_path):
    """External code review (round 5, medium, openai): a FALSY name
    (``null``, ``""``) used to be filtered out before being counted as
    rejected, so an all-null manifest read as "declared zero splits"
    (SKIPPED) instead of "every declared split was invalid" (loud)."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": None}, {"name": ""}, {"status": "x"}]}),
        encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "invalid/unsafe" in r.detail


def test_check_no_empty_split_fails_on_an_unreadable_spec_md(tmp_path):
    """External plan review (e2-checks-project-elicitation, round 1, medium):
    a declared split whose spec.md EXISTS but cannot be read must not
    silently drop out of every spec-text-keyed check as though the split
    didn't exist — that reads as a pass, not the unverifiable state it is.
    A directory named ``spec.md`` is the portable (cross-platform, unlike
    os.chmod on Windows) way to force a real read failure — same trick
    ``test_grill_trace_glossary.py`` already uses for this exact class of
    regression."""
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").mkdir()  # a directory, not a file — read_text() fails
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "unreadable/missing" in r.detail
    assert "01-a" in r.detail


def test_check_no_empty_split_fails_loud_on_a_malformed_project_config(tmp_path):
    """External code review (round 3, medium, GLM): a malformed
    ``shipwright_project_config.json`` used to fall through to "zero
    splits declared" and every spec-text gate passed vacuously — exactly
    the silent-pass failure mode round 1 closed for an unreadable
    spec.md, just one layer up (the manifest itself)."""
    (tmp_path / "shipwright_project_config.json").write_text(
        "{not valid json", encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "could not be parsed" in r.detail


def test_check_no_empty_split_fails_loud_on_a_mixed_manifest(tmp_path):
    """External Tier-3 review, PR #729: a MIXED manifest (one valid name
    alongside several unsafe ones) used to silently filter the unsafe
    entries and pass on the valid subset — a manifest containing
    ``01-a`` and ``../escape`` read as though only ``01-a`` were
    declared, letting the unsafe entry evade every gate. It must instead
    fail loud, same as an all-unsafe manifest, not crash the validator
    (non-string / absolute / traversal names are still handled without
    reaching ``planning_dir / name`` with a bad value)."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [
            {"name": "01-a"},
            {"name": "../escape"},
            {"name": "/absolute"},
            {"name": 42},
            {"name": None},
        ]}),
        encoding="utf-8",
    )
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget | Must | export widgets | interview |\n",
        encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)  # must not raise
    assert r.ok is False
    assert "invalid/unsafe" in r.detail


def test_check_no_empty_split_fails_loud_when_every_declared_name_is_unsafe(tmp_path):
    """External code review (round 4, low+medium, both reviewers): a
    manifest whose split names are ALL invalid/unsafe must not silently
    read as "zero splits declared" (SKIPPED) — that is a corrupt manifest,
    not an empty project, and deserves the same loud failure a totally
    unparseable config already gets."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "../escape"}, {"name": 42}, {"name": "."}]}),
        encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "invalid/unsafe" in r.detail


def test_check_no_empty_split_fails_loud_on_non_object_config(tmp_path):
    """External code review (round 6, medium, both reviewers
    independently): a syntactically valid but non-object config (``[]``)
    used to fall through to "zero splits declared" here even though the
    SAME case already failed loud in ``_read_project_scope`` — the
    inconsistency both reviewers independently caught."""
    (tmp_path / "shipwright_project_config.json").write_text("[]", encoding="utf-8")
    r = check_no_empty_split(tmp_path)  # must not raise
    assert r.ok is False
    assert "expected a JSON object" in r.detail


def test_check_no_empty_split_fails_loud_on_non_object_run_config_fallback(tmp_path):
    """Tier-3 PR review (PR #729): with no ``shipwright_project_config.json``
    written yet, the run-config FALLBACK path never validated ``data``'s
    shape the way the project-config branch does — a malformed, truthy
    non-dict ``shipwright_run_config.json`` (here a bare list) fell through
    to ``splits=[]``, SKIPPED, instead of failing loud like every other
    malformed-manifest case in this module."""
    (tmp_path / "shipwright_run_config.json").write_text("[1]", encoding="utf-8")
    r = check_no_empty_split(tmp_path)  # must not raise
    assert r.ok is False
    assert not r.is_skipped
    assert "expected a JSON object" in r.detail


def test_is_safe_split_name_rejects_windows_drive_and_root_relative_names():
    """External code review (round 6, low+medium, both reviewers
    independently): ``is_absolute()`` alone misses Windows DRIVE-relative
    (``"C:foo"``) and ROOT-relative (``"\\\\outside"``) names — neither
    counts as absolute to pathlib (it requires BOTH drive and root), but
    either re-anchors ``planning_dir / name`` away from the planning tree."""
    assert _is_safe_split_name("C:foo") is False
    assert _is_safe_split_name("\\outside\\spec") is False
    assert _is_safe_split_name("01-a") is True


def test_is_safe_split_name_rejects_backslash_traversal_on_any_host_os():
    """Required Tier-3 PR review (PR #729): the ``..``/``.`` segment check
    used to parse ``name`` with the host-native ``Path``, so a backslash
    traversal name stayed one literal part on POSIX (backslash isn't a
    separator there) and was judged safe — but the name is committed data
    later joined by whichever OS reads the manifest, where backslash IS a
    separator. Must be rejected regardless of which OS runs this check."""
    assert _is_safe_split_name("foo\\..\\..\\escape") is False


def test_check_no_empty_split_fails_loud_when_splits_is_not_a_list(tmp_path):
    """External code review (round 4, medium, openai): ``"splits": 1``
    (a scalar) used to raise ``TypeError`` iterating a non-iterable during
    manifest reading instead of producing a failing ``CheckResult``."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": 1}), encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)  # must not raise
    assert r.ok is False
    assert "expected a list" in r.detail


def test_check_no_empty_split_fails_on_a_declared_split_with_no_spec_md_at_all(tmp_path):
    """External CODE review (e2-checks-project-elicitation, round 2, medium):
    the round-1 fix only made an UNREADABLE spec.md fail loud — a DECLARED
    split that never got a spec.md written at all was still silently
    absent from ``_read_spec_texts``'s old ``*/spec.md`` glob, so a second
    populated split made this gate pass vacuously over the empty one."""
    _write_splits_config(tmp_path, ["01-a", "02-b"])
    populated = tmp_path / ".shipwright" / "planning" / "01-a"
    populated.mkdir(parents=True)
    (populated / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget | Must | export widgets | interview |\n",
        encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "planning" / "02-b").mkdir(parents=True)  # declared, spec.md never written
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "02-b" in r.detail
    assert "missing" in r.detail
    assert "01-a" not in r.detail


def test_check_no_empty_split_ignores_undeclared_planning_dirs(tmp_path):
    """External CODE review (e2-checks-project-elicitation, round 2, high,
    both reviewers independently): a raw directory-enumeration design
    cannot tell a real split from a reserved non-split dir under
    ``.shipwright/planning/`` (``campaigns/``, ``adr/``, ``grill-traces/``,
    ``iterate/``, ``01-adopted/`` — this very repo's own layout has all
    five) — an exclusion list chases every new one forever. The round-2
    redesign enumerates from the project's OWN declared ``splits``
    manifest instead, so an undeclared dir is invisible to this check
    regardless of its name, proven here with the two reserved dirs that
    actually broke it during review."""
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget | Must | export widgets | interview |\n",
        encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "planning" / "grill-traces").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "campaigns").mkdir(parents=True)
    r = check_no_empty_split(tmp_path)
    assert r.ok is True
