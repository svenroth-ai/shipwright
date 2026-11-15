"""check_skill_authoring.py: the measurable skill-authoring limits are read from the rules JSON and reported.

Each test builds a tiny throwaway skill and breaks exactly one limit, so a failure names it. No test reads the
real skills: CI runs this root, and an edit to a real skill must not red CI (the CLI is run by hand).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.tools import check_skill_authoring as csa  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")  # tooling for the skill-building rule used when changing a plugin; no AC is claimed

RULES = Path(csa.__file__).resolve().parents[2] / "config" / "conventions.json"
GOOD_FM = 'name: good-skill\ndescription: "Does a thing. Use when the user asks for the thing."\n'


def _skill(tmp_path: Path, frontmatter: str = GOOD_FM, body: str = "# T\n\ntext\n", refs: dict[str, str] | None = None) -> Path:
    d = tmp_path / "good-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    if refs:
        (d / "references").mkdir()
        for name, text in refs.items():
            (d / "references" / name).write_text(text, encoding="utf-8")
    return d


def _ids(skill: Path) -> set[str]:
    return {f["limit"] for f in csa.check_skill(skill, csa.load_limits(RULES))}


def test_rules_file_carries_every_limit_the_checker_reads() -> None:
    limits = csa.load_limits(RULES)
    for needed in ("name-required", "name-max-length", "name-charset", "name-reserved-words", "description-required", "description-max-length",
                   "no-xml-tags", "body-max-lines", "references-one-level", "reference-toc-threshold", "forward-slash-paths"):
        assert limits[needed]["checkable"] is True
    assert {k for k, v in limits.items() if v["kind"] == "runtime-cap"} == {"listing-description-cut", "post-compaction-skill-cap"}


def test_clean_skill_has_no_finding(tmp_path: Path) -> None:
    assert _ids(_skill(tmp_path)) == set()


@pytest.mark.parametrize("name,limit", [("x" * 65, "name-max-length"), ("Bad_Name", "name-charset"), ("my-claude-tool", "name-reserved-words")])
def test_name_limits(tmp_path: Path, name: str, limit: str) -> None:
    assert limit in _ids(_skill(tmp_path, f'name: {name}\ndescription: "ok"\n'))


def test_description_missing_and_too_long(tmp_path: Path) -> None:
    assert "description-required" in _ids(_skill(tmp_path, "name: good-skill\n"))
    d = tmp_path / "two"
    d.mkdir()
    long_fm = 'name: good-skill\ndescription: "' + "a" * 1025 + '"\n'
    (d / "SKILL.md").write_text(f"---\n{long_fm}---\nbody\n", encoding="utf-8")
    found = csa.check_skill(d, csa.load_limits(RULES))
    assert [f["limit"] for f in found] == ["description-max-length"]
    assert found[0]["kind"] == "hard"


def test_xml_tag_in_description(tmp_path: Path) -> None:
    assert "no-xml-tags" in _ids(_skill(tmp_path, 'name: good-skill\ndescription: "Use <b>bold</b> text"\n'))


def test_a_description_at_the_limit_passes(tmp_path: Path) -> None:
    assert _ids(_skill(tmp_path, 'name: good-skill\ndescription: "' + "a" * 1024 + '"\n')) == set()


def test_body_line_limit_counts_the_body_not_the_frontmatter(tmp_path: Path) -> None:
    limit = csa.load_limits(RULES)["body-max-lines"]["value"]
    assert "body-max-lines" not in _ids(_skill(tmp_path, body="\n".join(f"l{i}" for i in range(limit - 1)) + "\n"))
    other = tmp_path / "o"
    other.mkdir()
    assert "body-max-lines" in _ids(_skill(other, body="\n".join(f"l{i}" for i in range(limit)) + "\n"))  # Anthropic: "under 500"


def test_reference_not_linked_and_nested_reference(tmp_path: Path) -> None:
    skill = _skill(tmp_path, body="# T\n\nsee [a](references/a.md)\n", refs={"a.md": "# A\n\nsee [b](b.md)\n", "b.md": "# B\n", "c.md": "# C\n"})
    found = csa.check_skill(skill, csa.load_limits(RULES))
    messages = sorted(f["message"] for f in found if f["limit"] == "references-one-level")
    assert any("not linked" in m for m in messages)
    assert any("links on to another reference file: b.md" in m for m in messages)


def test_reference_linked_by_plain_path_counts_as_linked(tmp_path: Path) -> None:
    skill = _skill(tmp_path, body="# T\n\nRead `references/a.md` first.\n", refs={"a.md": "# A\n"})
    assert "references-one-level" not in _ids(skill)


def test_long_reference_needs_a_table_of_contents(tmp_path: Path) -> None:
    n = csa.load_limits(RULES)["reference-toc-threshold"]["value"]
    filler = "\n".join(f"line {i}" for i in range(n + 1))
    bad = _skill(tmp_path, body="[a](references/a.md)\n", refs={"a.md": "# A\n" + filler})
    assert "reference-toc-threshold" in _ids(bad)
    other = tmp_path / "o"
    other.mkdir()
    good = _skill(other, body="[a](references/a.md)\n", refs={"a.md": "# A\n\n## Contents\n\n- x\n" + filler})
    assert "reference-toc-threshold" not in _ids(good)


def test_backslash_path_is_found(tmp_path: Path) -> None:
    assert "forward-slash-paths" in _ids(_skill(tmp_path, body="Run scripts\\helper.py now\n"))


def test_frontmatter_block_scalar_is_read(tmp_path: Path) -> None:
    fields, body = csa.split_frontmatter("---\nname: a\ndescription: >\n  folded text\n  second line\n---\nbody\n")
    assert fields["name"] == "a"
    assert fields["description"] == "folded text second line"
    assert body.strip() == "body"


def test_cli_exit_codes_and_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean = _skill(tmp_path)
    assert csa.main(["--skill-dir", str(clean), "--rules", str(RULES)]) == 0
    soft = tmp_path / "s"
    soft.mkdir()
    long_body = "\n".join("x" for _ in range(csa.load_limits(RULES)["body-max-lines"]["value"] + 5))
    soft_skill = _skill(soft, body=long_body + "\n")
    assert csa.main(["--skill-dir", str(soft_skill)]) == 0  # recommended finding only
    assert csa.main(["--skill-dir", str(soft_skill), "--strict"]) == 1
    hard = tmp_path / "h"
    hard.mkdir()
    capsys.readouterr()
    assert csa.main(["--skill-dir", str(_skill(hard, "name: good-skill\n")), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["skills"] == 1
    assert [f["limit"] for f in payload["findings"]] == ["description-required"]


def test_cli_missing_input_is_exit_2(tmp_path: Path) -> None:
    assert csa.main(["--skill-dir", str(tmp_path / "nope")]) == 2
    assert csa.main([]) == 2
    assert csa.main(["--skill-dir", str(_skill(tmp_path)), "--rules", str(tmp_path / "missing.json")]) == 2


def test_find_skill_dirs_globs_the_plugins_layout(tmp_path: Path) -> None:
    (tmp_path / "plugins" / "p" / "skills" / "s").mkdir(parents=True)
    (tmp_path / "plugins" / "p" / "skills" / "s" / "SKILL.md").write_text("---\nname: s\n---\n", encoding="utf-8")
    assert [p.name for p in csa.find_skill_dirs(tmp_path)] == ["s"]


def test_missing_name_is_a_hard_finding(tmp_path: Path) -> None:
    skill = _skill(tmp_path, 'description: "ok"\n')
    found = csa.check_skill(skill, csa.load_limits(RULES))
    assert [(f["limit"], f["kind"]) for f in found] == [("name-required", "hard")]


def test_frontmatter_survives_bom_trailing_space_and_single_quotes() -> None:
    fields, body = csa.split_frontmatter("\ufeff---\nname: 'my-skill'\ndescription: 'It''s fine'\n--- \nbody\n")
    assert fields == {"name": "my-skill", "description": "It's fine"}
    assert body.strip() == "body"


def _nesting(skill: Path) -> list[str]:
    return [f["message"] for f in csa.check_skill(skill, csa.load_limits(RULES)) if f["limit"] == "references-one-level"]


def test_nested_reference_named_by_plain_path_is_found(tmp_path: Path) -> None:
    refs = {"a.md": "# A\n\nthen read references/b.md\n", "b.md": "# B\n"}
    skill = _skill(tmp_path, body="[a](references/a.md) [b](references/b.md)\n", refs=refs)
    assert _nesting(skill) == ["links on to another reference file: b.md"]


def test_a_link_to_a_same_named_file_elsewhere_does_not_count(tmp_path: Path) -> None:
    skill = _skill(tmp_path, body="see [a](../other-skill/references/a.md) and ../x/references/a.md\n", refs={"a.md": "# A\n"})
    assert _nesting(skill) == ["reference file is not linked from SKILL.md"]


def test_backslash_check_needs_a_word_boundary(tmp_path: Path) -> None:
    assert "forward-slash-paths" not in _ids(_skill(tmp_path, body="the transcripts\\x file\n"))


def test_all_with_no_skills_names_the_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert csa.main(["--all", "--repo-root", str(tmp_path)]) == 2
    assert "no plugins/*/skills/*/SKILL.md under" in capsys.readouterr().err

