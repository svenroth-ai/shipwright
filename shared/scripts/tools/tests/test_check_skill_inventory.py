"""check_skill_inventory.py: the migration inventory, truth table and subprocess map stay honest (DFP pilot P0).

Each test builds a tiny throwaway skill and breaks exactly one rule, so a failure names it. No test reads the real
changelog skill: CI runs this root, and an edit to that skill's prose must not red CI. The pilot's units run the CLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.tools import check_skill_inventory as csi  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.09")  # the tooling of the changelog skill's pilot; no AC is claimed

SKILL = "# T\n\nintro\n\n## Step 1\n\n```bash\n# not a heading\nrun\n```\n\n## Step 2\n\ntext\n"
PROMPT = "# Prompt\n\ntext\n"


def _cells() -> list[dict]:
    return [{"context": c, "autonomy": a, "question": q, "behaviour": "asks", "source": ["SRC"]}
            for c in csi.CONTEXTS for a in csi.AUTONOMY for q in csi.QUESTIONS]


def _inventory(skill: Path) -> dict:
    sections = [{"file": f, "path": p, "hash": h, "class": "mechanic", "target": "cli:prepare"}
                for (f, p), h in csi.live_anchors(skill).items()]
    for s in sections:
        if s["file"] == "references/prompt.md":
            s["class"], s["target"] = "runtime-input", "keep"
    return {"schema": 1, "runtime_inputs": [{"file": "references/prompt.md", "read_by": "reader.py"}], "sections": sections}


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path]:
    skill = tmp_path / "skill"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (skill / "references" / "prompt.md").write_text(PROMPT, encoding="utf-8")
    (tmp_path / "reader.py").write_text("PATH = 'references/prompt.md'\n", encoding="utf-8")
    (tmp_path / "SRC").write_text("a\nb\nc\n", encoding="utf-8")
    (skill / "inventory.json").write_text(json.dumps(_inventory(skill)), encoding="utf-8")
    (skill / "truth_table.json").write_text(json.dumps({"cells": _cells()}), encoding="utf-8")
    (skill / "subprocess_map.json").write_text(json.dumps({"entries": [
        {"file": "reader.py", "line": 1, "needle": "PATH", "plan": "offline"}]}), encoding="utf-8")
    return tmp_path, skill


def _edit(path: Path, fn) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def _only(errs: list[str], needle: str) -> None:
    assert len(errs) == 1 and needle in errs[0], errs


def test_a_consistent_skill_passes(repo):
    root, skill = repo
    assert csi.run(skill, root) == []


def test_fenced_comment_is_not_a_heading():
    assert [s["path"] for s in csi.parse_sections(SKILL)] == ["T", "T > Step 1", "T > Step 2"]


def test_a_fence_with_an_info_string_does_not_close_the_fence():
    text = "# T\n\n```\n```bash\n# still inside\n```\n\n## Real\n"
    assert [s["path"] for s in csi.parse_sections(text)] == ["T", "T > Real"]


def test_crlf_and_trailing_blanks_do_not_change_a_hash():
    assert csi.parse_sections(SKILL.replace("\n", "\r\n") + "\n\n") == csi.parse_sections(SKILL)


def test_a_repeated_heading_gets_a_numbered_anchor():
    assert [s["path"] for s in csi.parse_sections("# T\n\n## A\n\n## A\n")] == ["T", "T > A", "T > A #2"]


def test_a_new_section_must_be_inventoried(repo):
    root, skill = repo
    (skill / "SKILL.md").write_text(SKILL + "\n## Step 3\n\nnew\n", encoding="utf-8")
    _only(csi.run(skill, root), "section not inventoried")


def test_an_edited_section_is_stale_until_refreshed(repo):
    root, skill = repo
    (skill / "SKILL.md").write_text(SKILL.replace("text", "other text"), encoding="utf-8")
    _only(csi.run(skill, root), "stale hash")
    assert csi.run(skill, root, do_refresh=True) == []


def test_refresh_adds_new_sections_as_unclassified_which_still_fail(repo):
    root, skill = repo
    (skill / "SKILL.md").write_text(SKILL + "\n## Step 3\n\nnew\n", encoding="utf-8")
    _only(csi.run(skill, root, do_refresh=True), "unclassified")


def test_refresh_keeps_an_orphan_for_the_operator_to_see(repo):
    root, skill = repo
    (skill / "SKILL.md").write_text(SKILL.replace("## Step 2\n\ntext\n", ""), encoding="utf-8")
    _only(csi.run(skill, root, do_refresh=True), "orphan entry")


def test_an_entry_for_a_removed_section_is_an_orphan(repo):
    root, skill = repo
    (skill / "SKILL.md").write_text(SKILL.replace("## Step 2\n\ntext\n", ""), encoding="utf-8")
    _only(csi.run(skill, root), "orphan entry")


def test_a_duplicate_anchor_is_reported(repo):
    root, skill = repo
    _edit(skill / "inventory.json", lambda d: d["sections"].append(dict(d["sections"][0])))
    _only(csi.run(skill, root), "duplicate anchor")


def test_an_entry_without_file_or_path_is_reported_not_a_crash(repo):
    root, skill = repo
    _edit(skill / "inventory.json", lambda d: d["sections"].append({"class": "mechanic"}))
    _only(csi.run(skill, root), "lacks file or path")


def test_an_unknown_class_is_reported(repo):
    root, skill = repo
    _edit(skill / "inventory.json", lambda d: d["sections"][0].__setitem__("class", "vibes"))
    _only(csi.run(skill, root), "unknown class")


def test_an_unknown_target_is_reported(repo):
    root, skill = repo
    _edit(skill / "inventory.json", lambda d: d["sections"][0].__setitem__("target", "somewhere"))
    _only(csi.run(skill, root), "unknown target")


def test_a_mechanic_cannot_be_deleted(repo):
    root, skill = repo
    _edit(skill / "inventory.json", lambda d: d["sections"][0].__setitem__("target", "delete"))
    _only(csi.run(skill, root), "mechanic cannot be")


def test_a_mechanic_part_cannot_be_deleted_either(repo):
    root, skill = repo
    def mix(d):
        d["sections"][0].update({"class": "mixed", "target": "keep",
                                 "parts": [{"what": "x", "class": "mechanic", "target": "delete"}]})
    _edit(skill / "inventory.json", mix)
    _only(csi.run(skill, root), "mechanic cannot be")


def test_a_bad_part_class_is_reported(repo):
    root, skill = repo
    def mix(d):
        d["sections"][0].update({"class": "mixed", "target": "keep",
                                 "parts": [{"what": "x", "class": "vibes", "target": "keep"}]})
    _edit(skill / "inventory.json", mix)
    _only(csi.run(skill, root), "bad part class")


def test_a_mixed_section_must_list_its_parts(repo):
    root, skill = repo
    _edit(skill / "inventory.json", lambda d: d["sections"][1].__setitem__("class", "mixed"))
    _only(csi.run(skill, root), "mixed and parts disagree")


def test_a_runtime_input_must_be_kept(repo):
    root, skill = repo
    _edit(skill / "inventory.json", lambda d: [s.__setitem__("target", "delete") for s in d["sections"] if s["class"] == "runtime-input"])
    _only(csi.run(skill, root), "runtime-input must be keep")


def test_a_runtime_input_must_be_named_by_its_reader(repo):
    root, skill = repo
    (root / "reader.py").write_text("PATH = None\n", encoding="utf-8")
    _only(csi.run(skill, root), "does not name")


def test_a_runtime_input_file_must_exist(repo):
    root, skill = repo
    (skill / "references" / "prompt.md").unlink()
    errs = csi.run(skill, root)
    assert any("runtime input missing" in e for e in errs), errs


def test_the_runtime_input_class_and_the_runtime_list_must_agree(repo):
    root, skill = repo
    _edit(skill / "inventory.json", lambda d: d.__setitem__("runtime_inputs", []))
    _only(csi.run(skill, root), "disagree")


def test_the_truth_table_needs_every_cell(repo):
    root, skill = repo
    _edit(skill / "truth_table.json", lambda d: d["cells"].pop())
    _only(csi.run(skill, root), "missing cell")


def test_the_truth_table_refuses_a_duplicate_cell(repo):
    root, skill = repo
    _edit(skill / "truth_table.json", lambda d: d["cells"].append(dict(d["cells"][0])))
    _only(csi.run(skill, root), "duplicate cell")


def test_the_truth_table_refuses_an_unknown_cell(repo):
    root, skill = repo
    _edit(skill / "truth_table.json", lambda d: d["cells"].append({**d["cells"][0], "context": "elsewhere"}))
    _only(csi.run(skill, root), "unknown cell")


def test_the_truth_table_refuses_an_unknown_behaviour(repo):
    root, skill = repo
    _edit(skill / "truth_table.json", lambda d: d["cells"][0].__setitem__("behaviour", "dances"))
    _only(csi.run(skill, root), "unknown behaviour")


def test_a_cell_must_cite_a_source(repo):
    root, skill = repo
    _edit(skill / "truth_table.json", lambda d: d["cells"][0].__setitem__("source", []))
    _only(csi.run(skill, root), "cites no source")


@pytest.mark.parametrize("source,needle", [
    ("SRC:99", "out of range"), ("SRC:0", "invalid"), ("SRC:3-2", "invalid"),
    ("MISSING:1", "file missing"), ("a b c:1", "file missing")])
def test_a_cell_source_must_be_a_real_line(repo, source, needle):
    root, skill = repo
    _edit(skill / "truth_table.json", lambda d: d["cells"][0].__setitem__("source", [source]))
    _only(csi.run(skill, root), needle)


def test_a_cell_source_must_be_a_list(repo):
    root, skill = repo
    _edit(skill / "truth_table.json", lambda d: d["cells"][0].__setitem__("source", "SRC:1"))
    _only(csi.run(skill, root), "must be a list")


def test_a_moved_subprocess_line_is_reported(repo):
    root, skill = repo
    (root / "reader.py").write_text("# moved\nPATH = 'references/prompt.md'\n", encoding="utf-8")
    _only(csi.run(skill, root), "not found")


def test_a_subprocess_entry_needs_a_valid_plan_file_and_line(repo):
    root, skill = repo
    _edit(skill / "subprocess_map.json", lambda d: d["entries"][0].__setitem__("plan", "hope"))
    _only(csi.run(skill, root), "unknown plan")
    _edit(skill / "subprocess_map.json", lambda d: d["entries"][0].update({"plan": "seam", "file": "gone.py"}))
    _only(csi.run(skill, root), "file missing")
    _edit(skill / "subprocess_map.json", lambda d: d["entries"][0].update({"file": "reader.py", "line": "1"}))
    _only(csi.run(skill, root), "integer line range")
    for bad in ({"line": 0, "end": 1}, {"line": -1, "end": -1}, {"line": 2, "end": 1}, {"line": 1, "end": 10**6}):
        _edit(skill / "subprocess_map.json", lambda d, b=bad: d["entries"][0].update(b))
        _only(csi.run(skill, root), "integer line range")


def test_main_returns_0_when_consistent_and_1_when_not(repo, capsys):
    root, skill = repo
    assert csi.main(["--skill-dir", str(skill), "--repo-root", str(root)]) == 0
    assert "skill inventory: ok" in capsys.readouterr().out
    (skill / "SKILL.md").write_text(SKILL + "\n## Step 3\n", encoding="utf-8")
    assert csi.main(["--skill-dir", str(skill), "--repo-root", str(root), "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["errors"]


def test_refresh_through_main_rewrites_valid_json_even_without_a_header(repo):
    root, skill = repo
    (skill / "inventory.json").write_text(json.dumps({"sections": []}), encoding="utf-8")
    csi.main(["--skill-dir", str(skill), "--repo-root", str(root), "--refresh"])
    assert json.loads((skill / "inventory.json").read_text(encoding="utf-8"))["sections"]


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_an_unreadable_data_file_exits_2(repo, content):
    root, skill = repo
    (skill / "inventory.json").write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        csi.main(["--skill-dir", str(skill), "--repo-root", str(root)])
    assert exc.value.code == 2


def test_a_missing_skill_file_exits_2(repo):
    root, skill = repo
    (skill / "SKILL.md").unlink()
    with pytest.raises(SystemExit) as exc:
        csi.run(skill, root)
    assert exc.value.code == 2
