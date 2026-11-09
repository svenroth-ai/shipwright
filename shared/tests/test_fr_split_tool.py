"""atomic-frs U2: the ``fr_split`` tool end to end on a throwaway project (dry run, apply, restore, guards, exit codes)."""

from __future__ import annotations

import json

import pytest

from .fr_split_fixtures import GROUPING, _cut, _project, _snapshot
from lib.ac_move_map import parse_move_map
from tools import fr_split

pytestmark = pytest.mark.covers("FR-01.10")  # nearest FR: atomic-frs tooling has no catalog AC of its own yet (catalog_gap, how-only)


def test_dry_run_prints_the_diff_and_writes_nothing(tmp_path, capsys):
    root, cut = _project(tmp_path)
    before = _snapshot(root)
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut)]) == 0
    out = capsys.readouterr().out
    assert "conservation: ok" in out and "+### FR-01.03" in out and "Dry run: nothing written" in out
    assert _snapshot(root) == before


def test_apply_writes_spec_tags_and_baseline_and_a_second_run_still_checks_out(tmp_path):
    root, cut = _project(tmp_path)
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--apply", "--no-diff"]) == 0
    assert '"FR-01.03/AC04"' in (root / "tests/test_mail.py").read_text() or "FR-01.03/AC04" in (root / "tests/test_mail.py").read_text()
    assert "FR-01.01/AC04" not in (root / "tests/test_mail.py").read_text()
    assert '"FR-01.03/AC05"' in (root / "shipwright_ac_coverage_baseline.json").read_text()
    assert parse_move_map((root / ".shipwright/planning/01-core/spec.md").read_text())["FR-01.01/AC06"] == "FR-01.03/AC06"
    tests, _ = fr_split.collect_evidence(root)
    assert tests["FR-01.03.AC04"] == {"tests/test_mail.py::test_4"} and "FR-01.01.AC04" not in tests


def test_apply_restores_every_file_when_writing_fails_midway(tmp_path, monkeypatch):
    root, cut = _project(tmp_path)
    before = _snapshot(root)
    real, calls = fr_split._write, []

    def flaky(p, text):
        calls.append(p)
        if len(calls) == 3:
            raise OSError("disk full")  # the third write fails; the restore writes that follow go through
        real(p, text)
    monkeypatch.setattr(fr_split, "_write", flaky)
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--apply", "--no-diff"]) == 1
    assert _snapshot(root) == before


def test_a_test_that_names_criteria_of_two_parts_blocks_the_cut_unless_allowed(tmp_path, capsys):
    root, cut = _project(tmp_path, shared_test=True)
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--no-diff"]) == 1
    assert "share 1 test" in capsys.readouterr().out
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--no-diff", "--allow-shared-tests"]) == 0


def test_unusable_input_exits_two(tmp_path, capsys):
    root, cut = _project(tmp_path)
    cut.write_text(json.dumps({"source": "FR-01.01", "parts": []}), encoding="utf-8")
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut)]) == 2
    assert "cannot cut" in capsys.readouterr().err


def test_a_rejected_name_reaches_exit_one_through_the_tool(tmp_path, capsys):
    root, cut = _project(tmp_path)
    bad = {**GROUPING, "parts": [{**GROUPING["parts"][0], "title": "Runs mail_sender.py"}]}
    cut.write_text(json.dumps(bad), encoding="utf-8")
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--no-diff"]) == 1
    assert "implementation detail" in capsys.readouterr().out


def test_apply_restores_everything_when_the_regenerated_manifest_binds_differently(tmp_path, monkeypatch):
    root, cut = _project(tmp_path)
    manifest = root / fr_split.MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    node = lambda fr, test: {"requirements": {fr: {"id": fr, "acs": {"AC04": {"tests": {"unit": [{"id": test, "tag_source": "pytest_marker"}]}}}}}}  # noqa: E731
    manifest.write_text("{}", encoding="utf-8")
    before = _snapshot(root)
    calls = iter([node("FR-01.01", "t::a"), node("FR-01.03", "t::DIFFERENT")])
    monkeypatch.setattr(fr_split, "_regenerate_manifest", lambda _root: next(calls))
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--apply", "--no-diff"]) == 1
    assert _snapshot(root) == before


def test_a_missing_manifest_is_said_not_silently_skipped(tmp_path, capsys):
    root, cut = _project(tmp_path)
    fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--no-diff"])
    assert "manifest binding is not re-checked" in capsys.readouterr().out


def test_main_exits_two_for_a_grouping_that_is_not_an_object(tmp_path, capsys):
    root, cut = _project(tmp_path)
    cut.write_text("[]", encoding="utf-8")
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut)]) == 2


def test_two_parts_sharing_a_test_are_caught_even_when_the_titles_match(tmp_path, capsys):
    root, cut = _project(tmp_path, shared_test=True)
    g = {"source": "FR-01.01", "parts": [{"title": "Mail", "description": "Mail things.", "acs": [4, 5, 6]}]}
    cut.write_text(json.dumps(g), encoding="utf-8")
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--no-diff"]) == 1


def test_the_registry_keeps_the_high_water_mark_so_a_moved_number_is_never_minted_again(tmp_path):
    root, cut = _project(tmp_path)
    (root / "shipwright_ac_registry.json").write_text('{\n  "FR-01.01": 2\n}\n', encoding="utf-8")
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--apply", "--no-diff"]) == 0
    assert json.loads((root / "shipwright_ac_registry.json").read_text()) == {"FR-01.01": 6, "FR-01.03": 6}


def test_a_registry_created_by_a_failed_run_is_removed_again(tmp_path, monkeypatch):
    root, cut = _project(tmp_path)
    before = _snapshot(root)
    real = fr_split._write

    def flaky(p, text):
        if "test_mail" in str(p) and "backup" not in str(p) and not getattr(flaky, "fired", False):
            flaky.fired = True
            raise OSError("locked")
        real(p, text)
    monkeypatch.setattr(fr_split, "_write", flaky)
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--apply", "--no-diff"]) == 1
    assert _snapshot(root) == before  # incl. no leftover shipwright_ac_registry.json


def test_a_file_edited_while_the_run_was_waiting_is_never_overwritten(tmp_path, monkeypatch):
    root, cut = _project(tmp_path)
    manifest = root / fr_split.MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{}", encoding="utf-8")

    def regen(_root):
        (root / "tests/test_mail.py").write_text("# edited meanwhile\n", encoding="utf-8")
        return {}
    monkeypatch.setattr(fr_split, "_regenerate_manifest", regen)
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--apply", "--no-diff"]) == 1
    assert (root / "tests/test_mail.py").read_text() == "# edited meanwhile\n"
    assert "FR-01.03" not in (root / ".shipwright/planning/01-core/spec.md").read_text()


def test_uncommitted_changes_in_a_target_file_refuse_the_write(tmp_path, capsys):
    import subprocess
    root, cut = _project(tmp_path)
    git = lambda *a: subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=t", *a], cwd=root, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")
    (root / "tests/test_mail.py").write_text((root / "tests/test_mail.py").read_text() + "# local edit\n", encoding="utf-8")
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--apply", "--no-diff"]) == 2
    assert "uncommitted" in capsys.readouterr().err
    assert fr_split.main(["--project-root", str(root), "--grouping", str(cut), "--apply", "--no-diff", "--allow-dirty"]) == 0


def test_a_move_does_not_count_as_new_baseline_growth(tmp_path):
    import subprocess
    from tools.verifiers._ac_baseline_growth import baseline_grown_since_parent
    git = lambda *a: subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=t", *a], cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    (tmp_path / "b.json").write_text('{"schema_version": 1, "unbound": ["FR-01.01/AC04"]}', encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    new, *_ = _cut()
    (tmp_path / ".shipwright/planning/01-core").mkdir(parents=True)
    (tmp_path / ".shipwright/planning/01-core/spec.md").write_text(new, encoding="utf-8")
    assert baseline_grown_since_parent(tmp_path, tmp_path / "b.json", {"FR-01.03/AC04"}, "HEAD") == ([], [])
    assert baseline_grown_since_parent(tmp_path, tmp_path / "b.json", {"FR-01.03/AC07"}, "HEAD")[0] == ["FR-01.03/AC07"]


def test_a_criterion_moved_twice_is_still_not_new_baseline_growth(tmp_path):
    import subprocess
    from tools.verifiers._ac_baseline_growth import baseline_grown_since_parent
    git = lambda *a: subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=t", *a], cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    (tmp_path / "b.json").write_text('{"schema_version": 1, "unbound": ["FR-01.01/AC04"]}', encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    new, *_ = _cut()
    new = new.replace("| `FR-01.01/AC04` | `FR-01.03/AC04` |\n", "| `FR-01.01/AC04` | `FR-01.03/AC04` |\n| `FR-01.03/AC04` | `FR-01.04/AC04` |\n")
    (tmp_path / ".shipwright/planning/01-core").mkdir(parents=True)
    (tmp_path / ".shipwright/planning/01-core/spec.md").write_text(new, encoding="utf-8")
    assert baseline_grown_since_parent(tmp_path, tmp_path / "b.json", {"FR-01.04/AC04"}, "HEAD") == ([], [])
