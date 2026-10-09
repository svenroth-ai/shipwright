"""Test-tag gate: the three collector-side gaps left open by PR 861 (FR-01.11/AC42).

Each case builds a real git repo in ``tmp_path`` and runs the gate through the real compliance
collector: (1) a wrapped ``.each`` table holding a regex literal or JSX text, (2) a test folder
named only by the head config, (3) files dropped from the archived head by ``export-ignore``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from test_tag_binding_gate_integration import RUN, _py_base, _repo  # noqa: E402
from tools.verifiers import tag_binding_gate as gate  # noqa: E402

_CFG = "shipwright_compliance_config.json"
_LEGACY_BODY = "test('legacy', () => { expect(1).toBe(1); });\n"


@pytest.mark.covers("FR-01.11/AC42")
@pytest.mark.parametrize("table", [
    "[\n  [/it's/, 'x'],\n  [/b/, 'y'],\n]",
    "[\n  [/a(b/, 'x'],\n]",
    "[\n  ['<p>Don\\'t</p>', 'x'],\n]",
    "[\n  [<p>Don't (stop)</p>, 'x'],\n]",
], ids=["apostrophe-regex", "paren-regex", "escaped-quote", "jsx-text"])
def test_a_wrapped_table_with_a_regex_or_jsx_text_is_seen_by_the_gate(tmp_path, table):
    base = {**_py_base(), "tests/legacy.test.tsx": _LEGACY_BODY}
    head_test = f"it.each({table})('wrapped %s', (a, b) => {{\n  expect(a).toBe(a);\n}});\n"
    root, sha = _repo(tmp_path, base, {"tests/legacy.test.tsx": _LEGACY_BODY + head_test})
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is False, result.detail
    assert "untagged-added" in result.detail and "legacy.test.tsx::wrapped %s" in result.detail


@pytest.mark.covers("FR-01.11/AC42")
def test_the_gate_lexes_with_the_shared_lib_module():
    from lib import ts_lexer
    from tools.verifiers import _tag_binding_ts

    assert _tag_binding_ts.lex is ts_lexer.lex


@pytest.mark.covers("FR-01.11/AC42")
@pytest.mark.parametrize(("base_cfg", "head_cfg", "test_path"), [
    (None, {"test_roots": ["checks"]}, "checks/test_n.py"),
    (None, {"test_roots": ["plugins/*/qa"]}, "plugins/new/qa/test_n.py"),
    ({"test_roots": ["tests"]}, {"test_roots": ["tests", "checks"]}, "checks/test_n.py"),
    ({"test_roots": ["tests"]}, {"test_roots": ["checks"]}, "checks/test_n.py"),
], ids=["plain", "glob", "added-to-base-config", "replacing-base-config"])
def test_a_test_folder_named_only_by_the_head_config_is_seen(tmp_path, base_cfg, head_cfg, test_path):
    base = dict(_py_base())
    if base_cfg is not None:
        base[_CFG] = json.dumps({"traceability": base_cfg})
    head = {_CFG: json.dumps({"traceability": head_cfg}), test_path: "def test_brand_new():\n    pass\n"}
    root, sha = _repo(tmp_path, base, head)
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is False and f"{test_path}::test_brand_new" in result.detail, result.detail


@pytest.mark.covers("FR-01.11/AC42")
def test_a_test_hidden_by_export_ignore_at_head_is_still_seen(tmp_path):
    head = {".gitattributes": "tests/hidden export-ignore\n",
            "tests/hidden/test_h.py": "def test_hidden():\n    pass\n"}
    root, sha = _repo(tmp_path, _py_base(), head)
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is False and "tests/hidden/test_h.py::test_hidden" in result.detail, result.detail


@pytest.mark.covers("FR-01.11/AC42")
def test_a_base_test_under_export_ignore_does_not_read_as_removed_or_new(tmp_path):
    base = {**_py_base(), ".gitattributes": "tests/hidden export-ignore\n",
            "tests/hidden/test_h.py": "def test_hidden():\n    pass\n"}
    root, sha = _repo(tmp_path, base, {"tests/test_a.py": "def test_old():\n    assert 1 + 1 == 2\n# edit\n"})
    assert gate.check_test_tag_binding(root, RUN, sha).ok is True


def _stage_link(root: Path, path: str, target: str) -> None:
    import subprocess

    blob = subprocess.run(["git", "-C", str(root), "hash-object", "-w", "--stdin"], input=target.encode(),
                          capture_output=True, check=True).stdout.decode().strip()
    _git_out(root, "update-index", "--add", "--cacheinfo", f"120000,{blob},{path}")


@pytest.mark.covers("FR-01.11/AC42")
def test_a_materialised_tree_keeps_files_and_in_tree_file_links_only(tmp_path):
    from tools.verifiers._layer_coverage_regen import _archive_tree, clear_regen_cache

    root, sha = _repo(tmp_path, _py_base(), {"checks/impl.py": "def test_x():\n    pass\n"})
    clear_regen_cache()
    # Symlinks and a submodule gitlink are staged without needing OS symlink support.
    _stage_link(root, "tests/test_shadow.py", "../checks/impl.py")   # in-tree file: copied
    _stage_link(root, "tests/test_escape.py", "../../outside.py")     # leaves the tree: dropped
    _stage_link(root, "tests/test_dir.py", "../checks")               # a directory: dropped
    _git_out(root, "update-index", "--add", "--cacheinfo", f"160000,{sha},vendor/sub")
    _git_out(root, "-c", "user.email=t@t.dev", "-c", "user.name=t", "commit", "-q", "-m", "links")
    dest = tmp_path / "out"
    dest.mkdir()
    assert _archive_tree(root, _git_out(root, "rev-parse", "HEAD"), dest) is True
    assert (dest / "tests" / "test_a.py").is_file()
    assert (dest / "tests" / "test_shadow.py").read_text(encoding="utf-8") == "def test_x():\n    pass\n"
    for gone in ("tests/test_escape.py", "tests/test_dir.py", "vendor"):
        assert not (dest / gone).exists(), gone


@pytest.mark.covers("FR-01.11/AC42")
def test_a_symlinked_test_file_outside_the_test_roots_is_seen_by_the_gate(tmp_path):
    root, sha = _repo(tmp_path, _py_base(), {"checks/impl.py": "def test_x():\n    pass\n"})
    _stage_link(root, "tests/test_shadow.py", "../checks/impl.py")
    _git_out(root, "-c", "user.email=t@t.dev", "-c", "user.name=t", "commit", "-q", "-m", "link")
    result = gate.check_test_tag_binding(root, RUN, _git_out(root, "rev-parse", "HEAD"))
    assert result.ok is False and "tests/test_shadow.py::test_x" in result.detail, result.detail


@pytest.mark.covers("FR-01.11/AC42")
def test_an_empty_base_tree_is_a_valid_tree(tmp_path):
    import subprocess

    from tools.verifiers._layer_coverage_regen import _archive_tree

    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q"], ["-c", "user.email=t@t.dev", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    dest = tmp_path / "out"
    dest.mkdir()
    assert _archive_tree(root, "HEAD", dest) is True and not list(dest.iterdir())


def _git_out(root: Path, *args: str) -> str:
    from test_tag_binding_gate_integration import _git
    return _git(root, *args)


@pytest.mark.covers("FR-01.11/AC42")
def test_the_materialised_tree_keeps_an_export_ignored_folder(tmp_path):
    from tools.verifiers._layer_coverage_regen import _archive_tree

    base = {**_py_base(), ".gitattributes": "tests/hidden export-ignore\n",
            "tests/hidden/test_h.py": "def test_hidden():\n    pass\n"}
    root, _ = _repo(tmp_path, base, {})
    dest = tmp_path / "out"
    dest.mkdir()
    assert _archive_tree(root, "HEAD~0", dest) is True
    assert (dest / "tests" / "hidden" / "test_h.py").is_file()
