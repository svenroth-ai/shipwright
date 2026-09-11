"""Direct unit tests for ``verifiers._test_body_suspects`` (the P3.7 deferred
item, delivered bundled with P3.8) over a real git repo (``_keystone_repo.py``,
the same fixture module the P3.6/P3.7 keystone tests share).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from verifiers import _test_body_suspects as tbs  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import BASE_SPEC  # noqa: E402
from _keystone_repo import bound_manifest as _manifest_with_binding  # noqa: E402
from _keystone_repo import commit_all as _commit_all  # noqa: E402
from _keystone_repo import commit_spec as _commit_spec  # noqa: E402
from _keystone_repo import make_repo  # noqa: E402

_TEST_FILE = "tests/test_widget.py"

_ORIGINAL_BODY = """def test_fizz():
    assert widget.fizz() == "fizz"
"""

_EDITED_BODY = """def test_fizz():
    assert widget.fizz() == "fizz"
    assert widget.fizz.calls == 1
"""

_UNRELATED_ADDITION = """def test_fizz():
    assert widget.fizz() == "fizz"


def test_unrelated():
    assert True
"""


def _repo_with_test_file(tmp_path, body: str = _ORIGINAL_BODY):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / _TEST_FILE).write_text(body, encoding="utf-8")
    base_sha = _commit_all(root, "add test file")
    return root, base_sha


def _commit_body(root: Path, body: str, message: str) -> str:
    (root / _TEST_FILE).write_text(body, encoding="utf-8")
    return _commit_all(root, message)


def test_flags_a_body_edit_when_the_ac_criterion_is_unchanged(tmp_path):
    root, base_sha = _repo_with_test_file(tmp_path)
    head_sha = _commit_body(root, _EDITED_BODY, "edit the test body only")
    manifest = _manifest_with_binding()

    suspects, warnings = tbs.test_body_suspects(root, base_sha, head_sha, manifest, manifest)

    assert suspects == [
        {"fr_id": "FR-01.01", "ac_id": "AC01", "test_id": "tests/test_widget.py::test_fizz"},
    ]
    assert warnings == []


def test_an_unrelated_addition_leaves_the_bound_functions_body_untouched(tmp_path):
    """The bound test's own source segment is byte-identical even though the
    FILE changed (a second, unrelated function was added) -- no suspect."""
    root, base_sha = _repo_with_test_file(tmp_path)
    head_sha = _commit_body(root, _UNRELATED_ADDITION, "add an unrelated test")
    manifest = _manifest_with_binding()

    suspects, _ = tbs.test_body_suspects(root, base_sha, head_sha, manifest, manifest)

    assert suspects == []


def test_a_criterion_text_change_is_out_of_this_checks_territory(tmp_path):
    """A REAL AC edit (the criterion's own digest changes) is out of scope
    here even when the bound test's body ALSO changed in the same commit --
    that combination belongs to P3.6's own greenness walk, not this check."""
    root, base_sha = _repo_with_test_file(tmp_path)
    (root / _TEST_FILE).write_text(_EDITED_BODY, encoding="utf-8")
    head_sha = _commit_spec(
        root, BASE_SPEC.replace("The widget must fizz.", "The widget must fizz TWICE."),
        "edit AC01 text and the test body together",
    )
    manifest = _manifest_with_binding()

    suspects, _ = tbs.test_body_suspects(root, base_sha, head_sha, manifest, manifest)

    assert suspects == []


def test_a_newly_minted_ac_is_not_flagged(tmp_path):
    """``base_minted.get(key)`` absent (a criterion that does not exist yet
    at base) must never be treated as 'unchanged' -- it is a different,
    larger change (a brand-new AC), not a body-only suspect."""
    root, base_sha = _repo_with_test_file(tmp_path)
    (root / _TEST_FILE).write_text(_EDITED_BODY, encoding="utf-8")
    head_sha = _commit_spec(
        root,
        BASE_SPEC.replace(
            "- [AC02] The widget must buzz.",
            "- [AC02] The widget must buzz.\n- [AC04] The widget must also whirr.",
        ),
        "mint a brand-new AC and edit the test body together",
    )
    manifest = {
        "requirements": {
            "ns::FR-01.01": {
                "id": "FR-01.01", "status": "active", "spec_path": "docs/spec.md",
                "acs": {
                    "AC01": {"tests": {"unit": [
                        {"id": "tests/test_widget.py::test_fizz", "layer": "unit",
                         "status": "enabled", "executed": "pass"},
                    ]}},
                    "AC04": {"tests": {"unit": [
                        {"id": "tests/test_widget.py::test_fizz", "layer": "unit",
                         "status": "enabled", "executed": "pass"},
                    ]}},
                },
            },
        },
    }

    suspects, _ = tbs.test_body_suspects(root, base_sha, head_sha, manifest, manifest)

    # AC01's own body edit still fires; AC04 (brand new at head) never does.
    assert suspects == [
        {"fr_id": "FR-01.01", "ac_id": "AC01", "test_id": "tests/test_widget.py::test_fizz"},
    ]


def test_a_genuinely_absent_test_file_is_not_a_body_edit(tmp_path):
    """The bound test id names a file that was never committed at either
    commit -- absent-at-both-sides, not an edit; no crash, no suspect."""
    root, base_sha = _repo_with_test_file(tmp_path)
    manifest = {
        "requirements": {
            "ns::FR-01.01": {
                "id": "FR-01.01", "status": "active", "spec_path": "docs/spec.md",
                "acs": {"AC01": {"tests": {"unit": [
                    {"id": "tests/ghost.py::test_ghost", "layer": "unit",
                     "status": "enabled", "executed": "pass"},
                ]}}},
            },
        },
    }

    suspects, warnings = tbs.test_body_suspects(root, base_sha, base_sha, manifest, manifest)

    assert suspects == []
    assert warnings == []


def test_an_unrecognizable_test_id_warns_and_is_skipped(tmp_path):
    root, base_sha = _repo_with_test_file(tmp_path)
    manifest = {
        "requirements": {
            "ns::FR-01.01": {
                "id": "FR-01.01", "status": "active", "spec_path": "docs/spec.md",
                "acs": {"AC01": {"tests": {"unit": [
                    {"id": "not-a-pytest-node-id", "layer": "unit",
                     "status": "enabled", "executed": "pass"},
                ]}}},
            },
        },
    }

    suspects, warnings = tbs.test_body_suspects(root, base_sha, base_sha, manifest, manifest)

    assert suspects == []
    assert any("not a recognizable" in w for w in warnings)


def test_a_renamed_function_is_not_flagged(tmp_path):
    """The function named by the bound test id vanished from that file
    between base and head (renamed/moved) -- nothing to compare, no crash."""
    root, base_sha = _repo_with_test_file(tmp_path)
    head_sha = _commit_body(
        root, "def test_fizz_renamed():\n    assert widget.fizz() == \"fizz\"\n", "rename",
    )
    manifest = _manifest_with_binding()

    suspects, warnings = tbs.test_body_suspects(root, base_sha, head_sha, manifest, manifest)

    assert suspects == []
    assert warnings == []


def test_a_display_id_collision_is_excluded(tmp_path):
    root, base_sha = _repo_with_test_file(tmp_path)
    head_sha = _commit_body(root, _EDITED_BODY, "edit test body")
    colliding = {
        "requirements": {
            "ns::a": {
                "id": "FR-01.01", "status": "active", "spec_path": "docs/spec.md",
                "acs": {"AC01": {"tests": {"unit": [
                    {"id": "tests/test_widget.py::test_fizz", "layer": "unit",
                     "status": "enabled", "executed": "pass"},
                ]}}},
            },
            "ns::b": {"id": "FR-01.01", "status": "active", "spec_path": "docs/spec.md", "acs": {}},
        },
    }

    suspects, _ = tbs.test_body_suspects(root, base_sha, head_sha, colliding, colliding)

    assert suspects == []


def test_a_method_style_test_id_resolves_through_a_class(tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    (root / "tests").mkdir(parents=True, exist_ok=True)
    class_body = (
        "class TestWidget:\n"
        "    def test_fizz(self):\n"
        "        assert widget.fizz() == \"fizz\"\n"
    )
    (root / _TEST_FILE).write_text(class_body, encoding="utf-8")
    base_sha = _commit_all(root, "add class-scoped test")
    edited = (
        "class TestWidget:\n"
        "    def test_fizz(self):\n"
        "        assert widget.fizz() == \"fizz\"\n"
        "        assert True\n"
    )
    (root / _TEST_FILE).write_text(edited, encoding="utf-8")
    head_sha = _commit_all(root, "edit method body")
    manifest = {
        "requirements": {
            "ns::FR-01.01": {
                "id": "FR-01.01", "status": "active", "spec_path": "docs/spec.md",
                "acs": {"AC01": {"tests": {"unit": [
                    {"id": "tests/test_widget.py::TestWidget::test_fizz", "layer": "unit",
                     "status": "enabled", "executed": "pass"},
                ]}}},
            },
        },
    }

    suspects, _ = tbs.test_body_suspects(root, base_sha, head_sha, manifest, manifest)

    assert suspects == [
        {"fr_id": "FR-01.01", "ac_id": "AC01",
         "test_id": "tests/test_widget.py::TestWidget::test_fizz"},
    ]


def test_parse_test_id_rejects_non_python_and_empty_segments():
    assert tbs._parse_test_id("no-double-colon") is None
    assert tbs._parse_test_id("tests/x.txt::test_a") is None
    assert tbs._parse_test_id("tests/x.py::") is None


def test_function_source_returns_none_for_unparseable_text():
    assert tbs._function_source("def broken(:\n", ["test_a"]) is None
