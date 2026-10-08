"""The test-tag gate end to end: real git, the real compliance collector (FR-01.11/AC41, U1).

Every repo is built in ``tmp_path`` at run time (a ``main`` base commit, a ``feature``
head), so no untagged fixture test is ever committed to this repository.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.verifiers import tag_binding_gate as gate
from tools.verifiers._layer_coverage_regen import clear_regen_cache, regenerate_base_head
from tools.verifiers.iterate_checks import run_all_checks

RUN = "iterate-2026-10-08-tag-gate-it"
_SPEC = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-02.01 | Log in | Must | unit |\n\n### FR-02.01 — Log in\n\n"
    "- (E) [AC01] Given a user, when they log in, then they see the dashboard.\n"
)
_OLD = "def test_old():\n    assert 1 + 1 == 2\n"


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr}")
    return proc.stdout.strip()


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _commit(root: Path) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c")
    return _git(root, "rev-parse", "HEAD")


def _repo(tmp_path: Path, base: dict[str, str], head: dict[str, str], *, exemptions=None, branch=True) -> tuple[Path, str]:
    clear_regen_cache()
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    for key, value in (("user.email", "t@t.dev"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(root, "config", key, value)
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    _write(root, base)
    _commit(root)
    if branch:
        _git(root, "checkout", "-q", "-b", "feature")
    _write(root, head)
    entry = {"run_id": RUN, "complexity": "small", "type": "change"}
    if exemptions is not None:
        entry["exemptions"] = {"count": len(exemptions), "items": exemptions}
    (root / "shipwright_run_config.json").write_text(json.dumps({"iterate_history": [entry]}), encoding="utf-8")
    return root, _commit(root)


def _py_base() -> dict[str, str]:
    return {".shipwright/planning/app/spec.md": _SPEC, "tests/test_a.py": _OLD}


@pytest.mark.covers("FR-01.11/AC41")
def test_untagged_added_test_stops_naming_file_and_test(tmp_path):
    root, head = _repo(tmp_path, _py_base(), {"tests/test_a.py": _OLD + "\n\ndef test_new():\n    pass\n"})
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and not result.is_skipped
    assert "tests/test_a.py::test_new" in result.detail and "untagged-added" in result.detail


@pytest.mark.covers("FR-01.11/AC41")
def test_tagged_test_under_an_unchanged_ac_passes_and_is_linked(tmp_path):
    new = '\n\nimport pytest\n\n\n@pytest.mark.covers("FR-02.01/AC01")\ndef test_new():\n    pass\n'
    root, head = _repo(tmp_path, _py_base(), {"tests/test_a.py": _OLD + new})
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is True, result.detail
    _base, head_m, _ = regenerate_base_head(root, head, with_evidence=False)
    ac_links = head_m["requirements"]["02::FR-02.01"]["acs"]["AC01"]["tests"]
    assert any(link["id"] == "tests/test_a.py::test_new" for links in ac_links.values() for link in links)


@pytest.mark.covers("FR-01.11/AC41")
def test_class_mark_fixture_edit_and_docstring_edit_do_not_stop(tmp_path):
    base = {**_py_base(), "tests/fixtures/repo/tests/test_fake.py": "def test_fake():\n    pass\n"}
    head = {
        "tests/test_a.py": 'def test_old():\n    """Documented now."""\n    assert 1 + 1 == 2\n',
        "tests/fixtures/repo/tests/test_fake.py": "def test_fake():\n    pass\n\n\ndef test_more():\n    pass\n",
        "tests/test_cls.py": ('import pytest\n\n\n@pytest.mark.covers("FR-02.01")\nclass TestLogin:\n'
                              "    def test_one(self):\n        pass\n"),
    }
    root, sha = _repo(tmp_path, {**base, "shipwright_compliance_config.json": json.dumps(
        {"traceability": {"exclude_dirs": ["fixtures"]}})}, head)
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is True, result.detail


@pytest.mark.covers("FR-01.11/AC41")
def test_per_test_exemption_passes_and_a_per_diff_one_stops(tmp_path):
    helper = "\n\nclass Builders:\n    def test_data(self):\n        return 1\n"
    good = [{"kind": "test_exemption", "scope": "tests/test_a.py::test_data", "reason_code": "fixture-or-helper"}]
    root, head = _repo(tmp_path, _py_base(), {"tests/test_a.py": _OLD + helper}, exemptions=good)
    passed = gate.check_test_tag_binding(root, RUN, head)
    assert passed.ok is True and "exempted 1 of 1 added/edited tests (100%)" in passed.detail

    blanket = [{"kind": "test_exemption", "scope": "tests/test_a.py", "reason_code": "fixture-or-helper"}]
    root2, head2 = _repo(tmp_path / "b", _py_base(), {"tests/test_a.py": _OLD + helper}, exemptions=blanket)
    result = gate.check_test_tag_binding(root2, RUN, head2)
    assert result.ok is False and "per-diff or blanket" in result.detail


@pytest.mark.covers("FR-01.11/AC41")
def test_free_text_exemption_stops(tmp_path):
    free = [{"kind": "test_exemption", "scope": "tests/test_a.py::test_new", "reason_code": "trust me"}]
    root, head = _repo(tmp_path, _py_base(), {"tests/test_a.py": _OLD + "\n\ndef test_new():\n    pass\n"},
                       exemptions=free)
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and "closed test_exemption vocabulary" in result.detail


@pytest.mark.covers("FR-01.11/AC41")
def test_no_merge_base_or_no_collector_stops_never_skips(tmp_path, monkeypatch):
    root, head = _repo(tmp_path, _py_base(), {"tests/test_a.py": _OLD + "\n# x\n"}, branch=False)
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and not result.is_skipped and "cannot enforce" in result.detail

    root2, head2 = _repo(tmp_path / "c", _py_base(), {"tests/test_a.py": _OLD + "\n# x\n"})
    monkeypatch.setattr(gate, "regenerate_base_head", lambda *a, **k: None)
    result = gate.check_test_tag_binding(root2, RUN, head2)
    assert result.ok is False and "collector" in result.detail
    assert gate.check_test_tag_binding(root2, RUN, "").ok is False


@pytest.mark.covers("FR-01.11/AC41")
def test_webui_shaped_project_gets_the_gate_through_the_f11_check_list(tmp_path):
    base = {".shipwright/planning/app/spec.md": _SPEC,
            "e2e/login.spec.ts": "test('old', async ({ page }) => {\n  await page.goto('/');\n});\n"}
    wrapped = ("test(\n  'wrapped and tagged',\n  { tag: ['@FR-02.01'] },\n  async ({ page }) => {\n"
               "    await page.goto('/x');\n  },\n);\n"
               "test.describe('suite', { tag: ['@FR-02.01'] }, () => {\n"
               "  test('inherits', async () => {});\n});\n")
    root, head = _repo(tmp_path, base, {"e2e/login.spec.ts": base["e2e/login.spec.ts"] + wrapped})
    assert gate.check_test_tag_binding(root, RUN, head).ok is True

    untagged = "test(\n  'wrapped but untagged',\n  async ({ page }) => {\n    await page.goto('/y');\n  },\n);\n"
    root2, head2 = _repo(tmp_path / "w", base, {"e2e/login.spec.ts": base["e2e/login.spec.ts"] + untagged})
    results = {r.name: r for r in run_all_checks(root2, RUN, head2)}
    mine = results[gate.CHECK_NAME]
    assert mine.ok is False and "e2e/login.spec.ts::wrapped but untagged" in mine.detail


@pytest.mark.covers("FR-01.11/AC41")
def test_a_non_git_project_stops_with_a_remediation(tmp_path):
    result = gate.check_test_tag_binding(tmp_path, RUN, "abc")
    assert result.ok is False and not result.is_skipped
    assert "not a git work tree" in result.detail and "git work tree" in result.detail.split(" - ", 1)[1]


@pytest.mark.covers("FR-01.11/AC41")
def test_an_unused_exemption_warns_without_blocking(tmp_path):
    stray = [{"kind": "test_exemption", "scope": "tests/test_a.py::test_gone", "reason_code": "fixture-or-helper"}]
    tagged = '\n\nimport pytest\n\n\n@pytest.mark.covers("FR-02.01")\ndef test_new():\n    pass\n'
    root, head = _repo(tmp_path, _py_base(), {"tests/test_a.py": _OLD + tagged}, exemptions=stray)
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.severity == "warning" and result.strict_exempt and "unused" in result.detail
