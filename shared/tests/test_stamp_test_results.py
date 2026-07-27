"""Tests for ``stamp_test_results.py`` — call site 1 of the artifact-state stamp.

Card ``trg-4d5b6a56`` (FR-01.10). The test-results record is written by a prompt
(a heredoc in the test-runner agent, a ``Write`` at iterate F5), so the stamp is
applied by this tool immediately afterwards and every value it writes is resolved
by **code**. That is the point: the campaign's finding on the neighbouring
``mode: standalone`` field was that a prompt-typed field is not a control.

The preservation and idempotency cases here are the second half of this change's
voluntary Boundary Probe (see ``test_source_state.py`` for the format round-trip).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.tools.stamp_test_results import RESULTS_REL, main as stamp_main  # noqa: E402
from source_state import BLOCK_KEY, from_block  # noqa: E402

RUN = "iterate-2026-07-27-artifact-state-stamping"

# A realistically-shaped record: every layer plus the two top-level blocks the
# monorepo's own tracked file carries.
RECORD = {
    "schema_version": 2,
    "status": "pass",
    "unit": {"passed": 42, "total": 42, "duration_s": 8.3},
    "integration": {"passed": 12, "total": 12, "skipped": False},
    "smoke": {"status": "pass", "url": "http://localhost:3000"},
    "e2e": {"passed": 15, "total": 17, "skipped": False},
    "coverage": {"total": 84.2, "measured_tier": "repo"},
    "iterate_latest": {"run_id": "iterate-2026-07-26-something", "unit": {"total": 9}},
}


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", "-C", str(cwd), *args],
                   check=True, capture_output=True, text=True, timeout=30)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True, text=True, timeout=30)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    (tmp_path / "src.py").write_text("x = 1\n", encoding="utf-8")
    _write(tmp_path, RECORD)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", "initial"], tmp_path)
    return tmp_path


def _write(root: Path, data: dict) -> None:
    (root / RESULTS_REL).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read(root: Path) -> dict:
    return json.loads((root / RESULTS_REL).read_text(encoding="utf-8"))


def _run(root: Path, *extra: str) -> int:
    return stamp_main(["--project-root", str(root), *extra])


# --------------------------------------------------------------------------
# AC2 — the stamp lands, and nothing else in the record moves
# --------------------------------------------------------------------------


class TestStampAndPreserve:
    def test_writes_the_block_with_code_resolved_values(self, project: Path):
        assert _run(project, "--run-id", RUN) == 0
        state = from_block(_read(project)[BLOCK_KEY])
        assert state.run_id == RUN
        assert state.commit is not None and len(state.commit) == 40
        # The record itself is excluded from the dirty calculation, so a tree
        # whose only change is the record reads clean.
        assert state.dirty is False

    def test_every_other_top_level_key_is_preserved_with_its_value(self, project: Path):
        _run(project, "--run-id", RUN)
        after = _read(project)
        for key, value in RECORD.items():
            assert after[key] == value, f"{key} was altered"

    def test_key_order_is_preserved_and_the_stamp_is_appended(self, project: Path):
        _run(project, "--run-id", RUN)
        keys = list(_read(project).keys())
        assert keys == [*RECORD.keys(), BLOCK_KEY]

    def test_serialised_in_the_repo_canonical_form(self, project: Path):
        # Matches record_coverage_total.py — the other isolated writer of this same
        # file — so the two cannot fight over formatting on every run. Asserted on
        # BYTES: read_text() applies universal newlines, which would let a CRLF file
        # pass identically and leave the line-ending property untested — and that is
        # the actual formatting-fight risk on Windows.
        _run(project, "--run-id", RUN)
        raw = (project / RESULTS_REL).read_bytes()
        assert b"\r\n" not in raw, "CRLF would make the two writers fight every run"
        assert raw.endswith(b"}\n")
        assert raw == (json.dumps(_read(project), indent=2) + "\n").encode("utf-8")

    def test_a_real_source_change_is_reported_dirty(self, project: Path):
        (project / "src.py").write_text("x = 2\n", encoding="utf-8")
        _run(project, "--run-id", RUN)
        assert from_block(_read(project)[BLOCK_KEY]).dirty is True


# --------------------------------------------------------------------------
# AC8 — stamping twice equals stamping once
# --------------------------------------------------------------------------


class TestIdempotency:
    def test_second_run_replaces_rather_than_nests(self, project: Path):
        _run(project, "--run-id", RUN)
        first = (project / RESULTS_REL).read_text(encoding="utf-8")
        assert _run(project, "--run-id", RUN) == 0
        assert (project / RESULTS_REL).read_text(encoding="utf-8") == first
        block = _read(project)[BLOCK_KEY]
        assert BLOCK_KEY not in block
        assert set(block) == {"run_id", "commit", "dirty"}

    def test_restamping_with_a_new_run_id_overwrites(self, project: Path):
        _run(project, "--run-id", RUN)
        _run(project, "--run-id", "iterate-2026-07-28-later")
        assert _read(project)[BLOCK_KEY]["run_id"] == "iterate-2026-07-28-later"

    def test_a_preexisting_garbage_block_is_replaced(self, project: Path):
        _write(project, {**RECORD, BLOCK_KEY: "not-a-dict"})
        assert _run(project, "--run-id", RUN) == 0
        assert _read(project)[BLOCK_KEY]["run_id"] == RUN


# --------------------------------------------------------------------------
# AC9 / AC7 — refuse rather than destroy; degrade rather than crash
# --------------------------------------------------------------------------


class TestRefusalAndDegradation:
    def test_corrupt_record_is_never_overwritten(self, project: Path):
        corrupt = '{"unit": {"passed": 42,,,\n'
        (project / RESULTS_REL).write_text(corrupt, encoding="utf-8")
        assert _run(project, "--run-id", RUN) != 0
        # The whole point: a record we cannot read must survive untouched rather
        # than be replaced by a near-empty one that carries only a stamp.
        assert (project / RESULTS_REL).read_text(encoding="utf-8") == corrupt

    def test_a_json_array_record_is_refused(self, project: Path):
        (project / RESULTS_REL).write_text("[1, 2]\n", encoding="utf-8")
        assert _run(project, "--run-id", RUN) != 0
        assert (project / RESULTS_REL).read_text(encoding="utf-8") == "[1, 2]\n"

    def test_missing_record_is_refused_not_fabricated(self, project: Path):
        (project / RESULTS_REL).unlink()
        assert _run(project, "--run-id", RUN) != 0
        assert not (project / RESULTS_REL).exists()

    def test_no_git_still_stamps_the_run_id(self, tmp_path: Path):
        _write(tmp_path, RECORD)
        assert _run(tmp_path, "--run-id", RUN) == 0
        state = from_block(_read(tmp_path)[BLOCK_KEY])
        assert state.run_id == RUN
        assert state.commit is None
        assert state.dirty is None

    def test_unresolvable_run_id_is_null_not_invented(self, project: Path):
        assert _run(project) == 0
        assert _read(project)[BLOCK_KEY]["run_id"] is None

    def test_run_id_falls_back_to_the_run_config(self, project: Path):
        (project / "shipwright_run_config.json").write_text(
            json.dumps({"run_id": "pipeline-run-7"}), encoding="utf-8")
        assert _run(project) == 0
        assert _read(project)[BLOCK_KEY]["run_id"] == "pipeline-run-7"

    def test_an_explicit_run_id_wins_over_the_run_config(self, project: Path):
        (project / "shipwright_run_config.json").write_text(
            json.dumps({"run_id": "pipeline-run-7"}), encoding="utf-8")
        _run(project, "--run-id", RUN)
        assert _read(project)[BLOCK_KEY]["run_id"] == RUN

    def test_a_corrupt_run_config_does_not_break_stamping(self, project: Path):
        (project / "shipwright_run_config.json").write_text("{oops", encoding="utf-8")
        assert _run(project) == 0
        assert _read(project)[BLOCK_KEY]["run_id"] is None

    def test_an_unusable_run_id_is_refused_not_written(self, project: Path):
        assert _run(project, "--run-id", "bad\nvalue") == 0
        assert _read(project)[BLOCK_KEY]["run_id"] is None

    def test_explicit_results_path_is_honoured(self, project: Path):
        alt = project / "nested" / "other.json"
        alt.parent.mkdir()
        alt.write_text(json.dumps({"a": 1}) + "\n", encoding="utf-8")
        assert _run(project, "--run-id", RUN, "--results", str(alt)) == 0
        assert json.loads(alt.read_text(encoding="utf-8"))[BLOCK_KEY]["run_id"] == RUN
        assert BLOCK_KEY not in _read(project)


# --------------------------------------------------------------------------
# Boundary Probe — the 8 categories from references/boundary-probes.md
#
# Required because this change "introduces a NEW serialized format that any
# other code in the repo will read". Three categories are specific to operator-
# authored env files (POSIX `export` prefix, inline `# comment`, quoted values
# containing `#`) and are justified-skipped: neither format is an env file —
# one is a JSON object, the other a single generated markdown line — so those
# three inputs cannot occur. The remaining five are exercised for real.
# --------------------------------------------------------------------------


class TestBoundaryProbe:
    def test_bom_prefixed_record_is_read_and_written_without_a_bom(self, project: Path):
        raw = "\ufeff" + json.dumps(RECORD, indent=2) + "\n"
        (project / RESULTS_REL).write_text(raw, encoding="utf-8")
        assert _run(project, "--run-id", RUN) == 0
        text = (project / RESULTS_REL).read_text(encoding="utf-8")
        assert not text.startswith("\ufeff"), "a BOM was propagated into the record"
        assert _read(project)["unit"] == RECORD["unit"]

    def test_crlf_record_round_trips(self, project: Path):
        raw = (json.dumps(RECORD, indent=2) + "\n").replace("\n", "\r\n")
        (project / RESULTS_REL).write_bytes(raw.encode("utf-8"))
        assert _run(project, "--run-id", RUN) == 0
        assert _read(project)[BLOCK_KEY]["run_id"] == RUN

    def test_non_ascii_values_elsewhere_in_the_record_survive(self, project: Path):
        _write(project, {**RECORD, "note": "Prüfung — grün ✓"})
        assert _run(project, "--run-id", RUN) == 0
        assert _read(project)["note"] == "Prüfung — grün ✓"

    def test_a_non_ascii_run_id_round_trips(self, project: Path):
        assert _run(project, "--run-id", "iterate-2026-07-27-prüfung") == 0
        assert _read(project)[BLOCK_KEY]["run_id"] == "iterate-2026-07-27-prüfung"

    def test_a_hash_in_the_run_id_is_not_treated_as_a_comment(self, project: Path):
        # JSON has no comment syntax, so a `#` must survive verbatim rather than
        # truncating the value the way an env-file reader would.
        assert _run(project, "--run-id", "run#42") == 0
        assert _read(project)[BLOCK_KEY]["run_id"] == "run#42"

    def test_empty_run_id_is_null_not_empty_string(self, project: Path):
        assert _run(project, "--run-id", "") == 0
        assert _read(project)[BLOCK_KEY]["run_id"] is None

    def test_whitespace_only_run_id_is_null(self, project: Path):
        assert _run(project, "--run-id", "   ") == 0
        assert _read(project)[BLOCK_KEY]["run_id"] is None


class TestRunIdResolutionPrecedence:
    """A *rejected* run id must not fall through to a plausible wrong one.

    Found by the doubt reviewer: `run_id = declared or from_config` meant that
    `--run-id "{run_id}"` — the exact input the brace-guard exists for — resolved to
    `shipwright_run_config.json::run_id`, which in an iterate legitimately holds a
    different, older pipeline run id. So the guard swapped an obviously-broken value
    for a plausible wrong one, the opposite of the intent.
    """

    def test_a_rejected_run_id_does_not_fall_back_to_the_run_config(self, project: Path):
        (project / "shipwright_run_config.json").write_text(
            json.dumps({"run_id": "pipeline-run-7"}), encoding="utf-8")
        assert _run(project, "--run-id", "{run_id}") == 0
        assert _read(project)[BLOCK_KEY]["run_id"] is None

    def test_an_omitted_run_id_still_uses_the_run_config(self, project: Path):
        (project / "shipwright_run_config.json").write_text(
            json.dumps({"run_id": "pipeline-run-7"}), encoding="utf-8")
        assert _run(project) == 0
        assert _read(project)[BLOCK_KEY]["run_id"] == "pipeline-run-7"

    def test_wrong_tree_is_warned_about_via_the_records_own_run_id(self, project: Path, capsys):
        # The wrong-tree case: --project-root pointing at a different tree than the
        # one the record was written to. The record's own iterate_latest.run_id is the
        # only code-resolvable signal, so it is what the check uses.
        _run(project, "--run-id", "iterate-2026-07-27-different")
        err = capsys.readouterr().err
        assert "iterate_latest.run_id" in err
        assert "iterate-2026-07-26-something" in err

    def test_no_warning_when_the_record_agrees(self, project: Path, capsys):
        _run(project, "--run-id", RECORD["iterate_latest"]["run_id"])
        assert "WARNING" not in capsys.readouterr().err
