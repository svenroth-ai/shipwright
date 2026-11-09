"""Readers that compare the catalog at two commits read the ``## AC-Move-Map``: a moved criterion is not removed + added."""

from __future__ import annotations

import pytest

from lib.ac_move_map import moved_catalog
from lib.ac_record import changed_catalog

pytestmark = pytest.mark.covers("FR-01.10")  # nearest FR; atomic-frs tooling has no catalog AC of its own yet

BASE = """# Spec

### FR-01.01 — Widgets

- (E) [AC01] The widget must fizz.
- (E) [AC02] The widget must buzz.
"""
MOVE = "\n## AC-Move-Map\n\n| Old id | New id |\n|---|---|\n| `FR-01.01/AC01` | `FR-01.03/AC01` |\n"


def _head(text: str = "The widget must fizz.") -> str:
    body = BASE.replace("- (E) [AC01] The widget must fizz.\n", "")
    return body + f"\n### FR-01.03 — Fizzing\n\n- (E) [AC01] {text}\n" + MOVE


def _run(tmp_path, head: str):
    spec = tmp_path / "spec.md"
    spec.write_text(head, encoding="utf-8")
    import subprocess
    git = lambda *a: subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=t", *a], cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    spec.write_text(BASE, encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    spec.write_text(head, encoding="utf-8")
    return changed_catalog(tmp_path, "HEAD", None, ["spec.md"])


def test_moved_criterion_with_same_wording_is_neither_changed_nor_removed(tmp_path):
    assert _run(tmp_path, _head()) == ({}, set())


def test_moved_and_reworded_criterion_is_changed_not_removed(tmp_path):
    changed, removed = _run(tmp_path, _head("The widget must fizz loudly."))
    assert list(changed) == ["FR-01.03.AC01"] and removed == set()


def test_without_a_move_map_it_is_removed_plus_changed(tmp_path):
    changed, removed = _run(tmp_path, _head().replace(MOVE, ""))
    assert "FR-01.03.AC01" in changed and removed == {"FR-01.01.AC01"}


def _git_repo(tmp_path):
    import subprocess
    git = lambda *a: subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=t", *a], cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    return git


def test_a_criterion_moved_into_another_spec_file_is_neither_removed_nor_changed(tmp_path):
    git = _git_repo(tmp_path)
    (tmp_path / "a.md").write_text(BASE, encoding="utf-8")
    (tmp_path / "b.md").write_text("# Other\n\n### FR-02.01 — Other\n\n- (E) [AC01] It must hum.\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    (tmp_path / "a.md").write_text(BASE.replace("- (E) [AC01] The widget must fizz.\n", ""), encoding="utf-8")
    (tmp_path / "b.md").write_text("# Other\n\n### FR-02.01 — Other\n\n- (E) [AC01] It must hum.\n\n### FR-02.02 — Fizzing\n\n- (E) [AC01] The widget must fizz.\n"
                                   "\n## AC-Move-Map\n\n| Old id | New id |\n|---|---|\n| `FR-01.01/AC01` | `FR-02.02/AC01` |\n", encoding="utf-8")
    assert changed_catalog(tmp_path, "HEAD", None, ["a.md", "b.md"]) == ({}, set())


def test_a_two_hop_move_through_changed_catalog_is_neither_removed_nor_changed(tmp_path):
    two_hop = MOVE + "| `FR-01.03/AC01` | `FR-01.04/AC01` |\n"
    head = _head().replace("### FR-01.03 — Fizzing", "### FR-01.04 — Fizzing").replace(MOVE, two_hop)
    assert _run(tmp_path, head) == ({}, set())


def test_moved_catalog_follows_a_chain_and_leaves_other_keys():
    moves = {"FR-01.01/AC01": "FR-01.03/AC01", "FR-01.03/AC01": "FR-01.04/AC01"}
    assert moved_catalog({"FR-01.01.AC01": "a", "FR-01.01.AC02": "b"}, moves) == {"FR-01.04.AC01": "a", "FR-01.01.AC02": "b"}


def test_ac_history_of_a_moved_criterion_joins_the_runs_under_its_old_and_new_id(tmp_path):
    from lib import spec_chain as sc
    spec = tmp_path / ".shipwright/planning/01-core/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(MOVE, encoding="utf-8")
    events = [
        {"type": "work_completed", "adr_id": "iterate-2026-09-01-old", "ts": "1", "affected_acs": [{"ac": "FR-01.01.AC01", "disposition": "changed"}]},
        {"type": "work_completed", "adr_id": "iterate-2026-11-01-new", "ts": "2", "affected_acs": [{"ac": "FR-01.03.AC01", "disposition": "checked-unchanged"}]},
        {"type": "work_completed", "adr_id": "iterate-2026-10-01-other", "ts": "3", "affected_acs": [{"ac": "FR-01.01.AC02", "disposition": "changed"}]},
    ]
    for ask in ("FR-01.03.AC01", "FR-01.01.AC01"):
        got = sc.ac_history(tmp_path, ask, events, with_pr=False)
        assert {r["run_id"] for r in got["runs"]} == {"iterate-2026-09-01-old", "iterate-2026-11-01-new"}, ask


def test_fr_history_names_the_requirement_a_new_one_was_split_from(tmp_path):
    from lib.fr_change_history import change_history_for_fr
    from lib.fr_history_render import _render_text
    spec = tmp_path / ".shipwright/planning/01-core/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(MOVE, encoding="utf-8")
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    got = change_history_for_fr(tmp_path, "FR-01.03")
    assert got.split_from == ("FR-01.01",)
    assert "moved here from FR-01.01" in _render_text(got, got.coverage)
    assert change_history_for_fr(tmp_path, "FR-01.01").split_from == ()


def test_a_hand_written_row_onto_a_living_id_does_not_hide_a_removal(tmp_path):
    head = BASE.replace("- (E) [AC01] The widget must fizz.\n", "") + "\n## AC-Move-Map\n\n| Old id | New id |\n|---|---|\n| `FR-01.01/AC01` | `FR-01.01/AC02` |\n"
    changed, removed = _run(tmp_path, head)
    assert removed == {"FR-01.01.AC01"} and changed == {}


def test_two_sources_onto_one_target_leave_one_removal_visible(tmp_path):
    head = (BASE.replace("- (E) [AC01] The widget must fizz.\n", "").replace("- (E) [AC02] The widget must buzz.\n", "")
            + "\n### FR-01.03 — Both\n\n- (E) [AC01] The widget must buzz.\n"
            + "\n## AC-Move-Map\n\n| Old id | New id |\n|---|---|\n| `FR-01.01/AC01` | `FR-01.03/AC01` |\n| `FR-01.01/AC02` | `FR-01.03/AC01` |\n")
    changed, removed = _run(tmp_path, head)
    assert len(removed) == 1


def test_real_moves_is_the_one_rule_and_both_gate_readers_agree_with_it(tmp_path):
    from lib.ac_move_map import real_moves
    base = {("FR-01.01", "AC01"), ("FR-01.01", "AC02"), ("FR-01.02", "AC01")}
    cases = {
        "a fr_split move": ({"FR-01.01/AC01": "FR-01.03/AC01"}, {("FR-01.03", "AC01")}),
        "a renumbering": ({"FR-01.01/AC01": "FR-01.03/AC09"}, set()),
        "a merge into an existing FR": ({"FR-01.01/AC01": "FR-01.02/AC02"}, set()),
        "onto a living id": ({"FR-01.01/AC01": "FR-01.01/AC02"}, set()),
    }
    for name, (moves, expect) in cases.items():
        head = (base - {("FR-01.01", "AC01")}) | {(f, a) for f, a in (tuple(v.split("/")) for v in moves.values())}
        assert set(real_moves(base, head, moves)) == expect, name


def test_a_renumbering_row_does_not_hide_a_removal_in_the_catalog_diff(tmp_path):
    head = _head().replace("[AC01] The widget must fizz.", "[AC09] The widget must fizz.").replace("`FR-01.03/AC01`", "`FR-01.03/AC09`")
    changed, removed = _run(tmp_path, head)
    assert removed == {"FR-01.01.AC01"}


def test_history_can_be_asked_with_the_slash_id_the_move_map_uses(tmp_path):
    from lib import spec_chain as sc
    spec = tmp_path / ".shipwright/planning/01-core/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(MOVE, encoding="utf-8")
    events = [{"type": "work_completed", "adr_id": "iterate-2026-09-01-old", "ts": "1", "affected_acs": [{"ac": "FR-01.01.AC01", "disposition": "changed"}]}]
    assert {r["run_id"] for r in sc.ac_history(tmp_path, "FR-01.03/AC01", events, with_pr=False)["runs"]} == {"iterate-2026-09-01-old"}
