"""Architecture rules of a stack profile: rule shape, loader recovery, vocabulary drift, bundled profiles."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_architecture_rules as par  # noqa: E402
import profile_resolver as pr  # noqa: E402
from lib import constitution_register as cr  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC13")
ROOT = Path(__file__).resolve().parents[2]


def rule(**kw) -> dict:
    base = {"id": "r1", "text": "A sentence.", "why": "Because.", "enforcement": "prompt-only (judgement)"}
    return {**base, **kw}


LINT = {"tool": "eslint", "target": "eslint.config.mjs", "block": {"rules": {"no-restricted-imports": "error"}}}


@pytest.mark.covers("FR-01.10/AC17")
def test_vocabulary_copy_equals_constitution_register():
    assert par.ENFORCEMENT == cr.ENFORCEMENT
    assert set(par.ALLOWED) == set(par.ENFORCEMENT)  # every class has an entry in the combination table


def test_valid_objects_of_every_class_load():
    rules = [
        rule(id="a"), rule(id="b", enforcement="validator", lint=LINT),
        rule(id="c", enforcement="validator", mechanism=["shared/x.py"]),
        rule(id="d", enforcement="hook", mechanism=["shared/x.py"]),
        rule(id="e", enforcement="test", mechanism=["shared/x.py"]),
        rule(id="f", enforcement="prompt-only (mechanisable)", note="no checker is wired in"),
        rule(id="g", enforcement="unimplemented", note="planned"),
    ]
    rs = par.load_rules(rules)
    assert rs.errors == [] and rs.warnings == [] and [r.id for r in rs.rules] == list("abcdefg")


@pytest.mark.parametrize("bad", [
    rule(enforcement="validator", lint=LINT, mechanism=["a.py"]),          # both
    rule(enforcement="validator"),                                          # needs one
    rule(enforcement="hook"), rule(enforcement="test"),                     # need a mechanism
    rule(enforcement="validator", lint={**LINT, "block": {"files": ["a"]}}),  # eslint block needs rules
    rule(enforcement="hook", lint=LINT),                                    # lint only with validator
    rule(enforcement="prompt-only (judgement)", mechanism=["a.py"]),       # mechanism not allowed
    rule(enforcement="nope"),                                               # outside vocabulary
    rule(enforcement="prompt-only (mechanisable)"),                         # needs a note
    rule(enforcement="unimplemented"),                                      # needs a note
    rule(why=""), rule(text=5), rule(note=3),
    rule(id="Bad Id"), {"text": "x", "why": "y", "enforcement": "unimplemented"},  # no id
    rule(enforcement="test", mechanism=[]), rule(enforcement="test", mechanism="a.py"),
    rule(enforcement="test", mechanism=["/abs.py"]), rule(enforcement="test", mechanism=["C:/x.py"]),
    rule(enforcement="test", mechanism=["../x.py"]), rule(enforcement="test", mechanism=["a\\b.py"]),
    rule(enforcement="test", mechanism=["a//b.py"]),
    rule(enforcement="validator", lint={**LINT, "tool": "pylint"}),
    rule(enforcement="validator", lint={**LINT, "block": {}}),
    rule(enforcement="validator", lint={**LINT, "target": "../x"}),
    rule(enforcement="validator", lint="eslint"),
    "", 7,
])
def test_bad_rule_is_an_error_and_dropped(bad):
    rs = par.load_rules([rule(id="ok"), bad])
    assert [r.id for r in rs.rules] == ["ok"] and len(rs.errors) == 1


@pytest.mark.covers("FR-01.01/AC15")
def test_lint_plus_mechanism_keeps_the_other_rules():
    rs = par.load_rules([rule(id="a"), rule(id="b", enforcement="validator", lint=LINT, mechanism=["x.py"]), rule(id="c")])
    assert [r.id for r in rs.rules] == ["a", "c"]
    assert len(rs.errors) == 1 and "never both" in rs.errors[0] and "rule b" in rs.errors[0]


def test_duplicate_id_first_wins():
    rs = par.load_rules([rule(text="first"), rule(text="second")])
    assert [r.text for r in rs.rules] == ["first"] and "duplicate" in rs.errors[0]


@pytest.mark.covers("FR-01.01/AC14")
def test_legacy_strings_normalised_with_one_warning_and_undeclared_class():
    rs = par.load_rules(["One.", "Two."])
    assert [(r.id, r.legacy, r.enforcement) for r in rs.rules] == [("legacy-string-1", True, None), ("legacy-string-2", True, None)]
    assert rs.errors == [] and len(rs.warnings) == 1 and "old plain-sentence" in rs.warnings[0]


def test_mixed_list_and_legacy_id_collision_declared_object_wins():
    rs = par.load_rules(["Old.", rule(id="legacy-string-1", text="declared")])
    assert [(r.id, r.text) for r in rs.rules] == [("legacy-string-1", "declared")]
    assert any("legacy sentence collides" in e for e in rs.errors)
    mixed = par.load_rules([rule(id="a"), "Old."])
    assert [r.id for r in mixed.rules] == ["a", "legacy-string-2"]


def test_absent_null_empty_and_wrong_type():
    assert par.load_rules(None).declared is False
    empty = par.load_rules([])
    assert empty.declared is True and empty.rules == [] and empty.errors == [] and empty.warnings == []
    wrong = par.load_rules({"id": "x"})
    assert wrong.rules == [] and "must be a list" in wrong.errors[0] and wrong.declared is False


def test_mixed_type_keys_never_raise():
    rs = par.load_rules([{**rule(), 5: "x", "zz": 1}])
    assert len(rs.rules) == 1 and rs.errors == [] and "'5'" in rs.warnings[0] and "'zz'" in rs.warnings[0]


def test_unknown_key_warns_but_comment_keys_do_not():
    rs = par.load_rules([rule(notes="typo", _comment="fine")])
    assert len(rs.rules) == 1 and rs.errors == [] and len(rs.warnings) == 1 and "'notes'" in rs.warnings[0]


def test_shadow_warning_survives_a_corrupt_bundled_file(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "x.json").write_text("{not json", encoding="utf-8")
    assert par.shadow_rules_warning({}, [str(bundled / "x.json")], str(bundled)) is None
    assert par.shadow_rules_warning({}, [str(bundled / "gone.json")], str(bundled)) is None


def test_check_paths_existence_and_escape(tmp_path):
    root = tmp_path / "proj"
    (root / "shared").mkdir(parents=True)
    (root / "shared" / "x.py").write_text("", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "y.py").write_text("", encoding="utf-8")
    rules = par.load_rules([
        rule(id="ok", enforcement="test", mechanism=["shared/x.py"]),
        rule(id="gone", enforcement="test", mechanism=["shared/missing.py"]),
        rule(id="cfg", enforcement="validator", lint=LINT),  # lint target need not exist yet
    ]).rules
    assert par.check_paths(rules, root) == [("gone", "mechanism 'shared/missing.py' does not exist")]
    link = root / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    esc = par.load_rules([rule(id="esc", enforcement="test", mechanism=["link/y.py"])]).rules
    assert par.check_paths(esc, root) == [("esc", "path 'link/y.py' resolves outside the project root")]


def _bundled(name: str) -> dict:
    return json.loads((ROOT / "shared" / "profiles" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", pr.bundled_names())
def test_every_bundled_profile_validates_and_its_rules_load(name):
    res = pr.resolve_profile(name, None, search_dirs=[("bundled", pr.bundled_dir())])
    rs = par.load_rules(res.data.get("architecture_rules"))
    assert rs.errors == []
    # bundled mechanism/lint paths exist in the repo (runtime validate does not check them: the cache layout differs)
    assert par.check_paths(rs.rules, ROOT) == []


def test_bundled_declared_rules_are_pinned():
    """U1 declares no bundled mechanism; a unit that adds one must also extend this expectation."""
    objs = {n: par.load_rules(_bundled(n).get("architecture_rules")) for n in pr.bundled_names()}
    assert [n for n, rs in objs.items() if any(r.mechanism or r.lint for r in rs.rules)] == []
    assert objs["vite-hono"].declared and objs["vite-hono"].rules == []
    assert objs["skill-companion-app"].declared and objs["skill-companion-app"].rules == []
    assert len(objs["supabase-nextjs"].rules) == 6 and all(r.legacy for r in objs["supabase-nextjs"].rules)


def test_shadow_warning_is_emitted_for_a_readable_bundled_file_with_rules(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "x.json").write_text(json.dumps({"architecture_rules": ["a", "b"]}), encoding="utf-8")
    (bundled / "empty.json").write_text(json.dumps({"architecture_rules": []}), encoding="utf-8")
    msg = par.shadow_rules_warning({}, [str(bundled / "x.json")], str(bundled))
    assert msg and "declares 2" in msg
    assert par.shadow_rules_warning({"architecture_rules": []}, [str(bundled / "x.json")], str(bundled)) is None
    assert par.shadow_rules_warning({}, [str(bundled / "empty.json")], str(bundled)) is None


def test_first_use_of_an_id_owns_it_even_when_that_rule_is_invalid():
    rs = par.load_rules([rule(id="a", why=""), rule(id="a", text="second")])
    assert rs.rules == [] and "'why'" in rs.errors[0] and "duplicate" in rs.errors[1]
