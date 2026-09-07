"""Unit tests for ``tools/backfill_ac_provenance.py``'s pure logic: the
multiply-claimed-file conflict guard and the write pass (upgrade / insert /
skip). The git correlation (``_commits_for_run_id`` / ``_added_test_files`` /
``_is_shallow_clone``) is tested separately, against a REAL throwaway repo, in
the sibling ``test_backfill_ac_provenance_cli_git.py`` (split out at the
300-LOC bloat-baseline threshold — see that file's docstring for why a real
repo, not a fake). The ``apply_upgrades`` skip-branches (non-Python file,
file-absent-at-head, unreadable file, syntax-error enumeration, decorator-only
substitution) are split further into
``test_backfill_ac_provenance_apply_skips.py``, for the same reason.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

_SPEC = importlib.util.spec_from_file_location(
    "backfill_ac_provenance_cli", _TOOLS / "backfill_ac_provenance.py",
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)  # type: ignore[union-attr]

_APPLY_SPEC = importlib.util.spec_from_file_location(
    "backfill_ac_provenance_apply", _TOOLS / "_backfill_ac_provenance_apply.py",
)
apply_mod = importlib.util.module_from_spec(_APPLY_SPEC)
_APPLY_SPEC.loader.exec_module(apply_mod)  # type: ignore[union-attr]


def _candidate(fr_id, ac_id, files, status="candidate"):
    return {"fr_id": fr_id, "ac_id": ac_id, "slug": f"iterate-{fr_id}-{ac_id}".lower(),
             "commit": "deadbeef", "status": status, "test_files": list(files)}


# --------------------------------------------------------------------------- #
# _mark_multiply_claimed_files                                                #
# --------------------------------------------------------------------------- #

def test_a_file_claimed_by_only_one_candidate_is_untouched():
    candidates = [_candidate("FR-01.01", "AC01", ["a/test_x.py"])]
    mod._mark_multiply_claimed_files(candidates)
    assert candidates[0]["status"] == "candidate"
    assert candidates[0]["test_files"] == ["a/test_x.py"]


def test_a_file_claimed_by_two_different_acs_is_dropped_from_both():
    candidates = [
        _candidate("FR-01.01", "AC01", ["a/test_shared.py", "a/test_only_one.py"]),
        _candidate("FR-01.02", "AC03", ["a/test_shared.py"]),
    ]
    mod._mark_multiply_claimed_files(candidates)
    assert candidates[0]["test_files"] == ["a/test_only_one.py"]
    assert candidates[0]["conflicted_test_files"] == ["a/test_shared.py"]
    assert candidates[1]["test_files"] == []
    assert candidates[1]["status"] == "all_test_files_conflicted"


def test_a_non_candidate_entry_is_never_inspected():
    candidates = [{"fr_id": "FR-01.01", "ac_id": "AC01", "status": "no_commit_found"}]
    mod._mark_multiply_claimed_files(candidates)  # must not raise on the missing key
    assert candidates[0]["status"] == "no_commit_found"


# --------------------------------------------------------------------------- #
# apply_upgrades                                                              #
# --------------------------------------------------------------------------- #

_UNTAGGED = '''"""A fixture test module."""
from __future__ import annotations


def test_one():
    assert True


def test_two():
    assert True
'''

_BARE_TAGGED = '''"""A fixture test module with an existing bare tag."""
from __future__ import annotations

import pytest


@pytest.mark.covers("FR-01.01")
def test_one():
    assert True
'''

_OTHER_TAGGED = '''"""A fixture test module already tagged for something else."""
from __future__ import annotations

import pytest


@pytest.mark.covers("FR-09.09")
def test_one():
    assert True
'''

def test_apply_upgrades_inserts_a_new_ac_scoped_tag_on_an_untagged_test(tmp_path):
    rel = "tests/test_untagged.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_UNTAGGED, encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["tags_inserted_total"] == 2
    assert result["upgraded_bare_tags"] == []
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text.count('@pytest.mark.covers("FR-01.01/AC01")') == 2


def test_apply_upgrades_widens_an_existing_bare_tag(tmp_path):
    rel = "tests/test_bare.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_BARE_TAGGED, encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["tags_upgraded_total"] == 1
    assert result["tags_inserted_total"] == 0
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert 'covers("FR-01.01/AC01")' in text
    assert 'covers("FR-01.01")' not in text


def test_apply_upgrades_never_touches_a_test_already_tagged_for_something_else(tmp_path):
    rel = "tests/test_other.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_OTHER_TAGGED, encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["tags_inserted_total"] == 0
    assert result["upgraded_bare_tags"] == []
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text == _OTHER_TAGGED  # byte-identical: nothing written


def test_apply_upgrades_reports_a_non_candidate_status_untouched(tmp_path):
    report = {"candidates": [_candidate("FR-01.01", "AC01", [], status="no_commit_found")]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result == {
        "upgraded_bare_tags": [], "inserted_new_tags": [], "skipped": [],
        "tags_upgraded_total": 0, "tags_inserted_total": 0,
    }


def test_apply_upgrades_is_idempotent_on_rerun(tmp_path):
    """External plan review (P3.4): re-running against its own output must
    write nothing new — the exact no-guess, no-duplicate-tag property the
    review asked to see demonstrated."""
    rel = "tests/test_untagged.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_UNTAGGED, encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    first = apply_mod.apply_upgrades(tmp_path, report)
    assert first["tags_inserted_total"] == 2
    second = apply_mod.apply_upgrades(tmp_path, report)
    assert second["tags_inserted_total"] == 0
    assert second["upgraded_bare_tags"] == []
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text.count('@pytest.mark.covers("FR-01.01/AC01")') == 2  # not 4


# --------------------------------------------------------------------------- #
# validate_applied                                                            #
# --------------------------------------------------------------------------- #

_MINTED_SPEC = (
    "### FR-01.01 — /shipwright-run\n\n"
    "- (E) [AC01] Given a described change, when the pipeline is run, then\n"
    "  the phases are carried out in order.\n"
)


def test_validate_applied_passes_when_every_written_ac_exists(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_MINTED_SPEC, encoding="utf-8")
    apply_result = {"upgraded_bare_tags": [], "inserted_new_tags": [
        {"file": "t.py", "fr_id": "FR-01.01", "ac_id": "AC01"},
    ]}
    assert apply_mod.validate_applied(tmp_path, apply_result, spec) == []


def test_validate_applied_flags_a_written_ac_that_does_not_resolve(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_MINTED_SPEC, encoding="utf-8")
    apply_result = {"upgraded_bare_tags": [], "inserted_new_tags": [
        {"file": "t.py", "fr_id": "FR-01.01", "ac_id": "AC99"},  # never minted
    ]}
    assert apply_mod.validate_applied(tmp_path, apply_result, spec) == ["FR-01.01/AC99"]


# --------------------------------------------------------------------------- #
# main() -- orphan rollback                                                   #
# --------------------------------------------------------------------------- #

def test_main_rolls_back_every_touched_file_when_an_orphan_tag_is_written(tmp_path, monkeypatch):
    """External plan review + external code review (P3.4, glm low / openai
    medium): a post-write orphan must not leave a half-applied tree behind a
    non-zero exit -- every file this run touched is restored byte-for-byte."""
    rel = "tests/test_untagged.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_UNTAGGED, encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text("### FR-01.01 — /shipwright-run\n\nno minted ACs here.\n", encoding="utf-8")

    fake_report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    monkeypatch.setattr(mod, "_is_shallow_clone", lambda *_: False)
    monkeypatch.setattr(mod, "derive", lambda *_a, **_k: fake_report)

    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec), "--write"])

    assert rc == 1
    assert (tmp_path / rel).read_text(encoding="utf-8") == _UNTAGGED  # restored, not left half-written


# --------------------------------------------------------------------------- #
# derive() status accounting                                                  #
# --------------------------------------------------------------------------- #

def test_derive_status_counts_never_folds_a_conflict_into_candidate_count():
    candidates = [
        _candidate("FR-01.01", "AC01", ["a/test_shared.py"]),
        _candidate("FR-01.02", "AC03", ["a/test_shared.py"]),
        {"fr_id": "FR-01.05", "ac_id": "AC02", "slug": "x", "status": "no_commit_found",
         "commit_count": 0},
    ]
    mod._mark_multiply_claimed_files(candidates)
    status_counts: dict[str, int] = {}
    for cand in candidates:
        status_counts[cand["status"]] = status_counts.get(cand["status"], 0) + 1
    assert status_counts == {"all_test_files_conflicted": 2, "no_commit_found": 1}
