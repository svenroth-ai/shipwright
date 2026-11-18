"""The infrastructure class end to end: real git, the real collector, the catalog read at the merge-base (FR-01.11/AC55)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.verifiers import tag_binding_gate as gate
from tools.verifiers._layer_coverage_regen import clear_regen_cache
from tools.verifiers._tag_binding_infra_pass import CATALOG_PATH

pytestmark = pytest.mark.covers("FR-01.11/AC55")

RUN = "iterate-2026-11-18-infra-gate-it"
_SPEC = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-02.01 | Log in | Must | unit |\n\n### FR-02.01 — Log in\n\n"
    "- (E) [AC01] Given a user, when they log in, then they see the dashboard.\n"
)
_OLD = "def test_old():\n    assert 1 + 1 == 2\n"
_MARKED = '\n\nimport pytest\n\n\n@pytest.mark.covers_none("infra")\ndef test_probe():\n    assert True\n'


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


def _repo(tmp_path: Path, base: dict[str, str], head: dict[str, str]) -> tuple[Path, str]:
    clear_regen_cache()
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    for key, value in (("user.email", "t@t.dev"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(root, "config", key, value)
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    _write(root, base)
    _commit(root)
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, head)
    entry = {"run_id": RUN, "complexity": "small", "type": "change"}
    (root / "shipwright_run_config.json").write_text(json.dumps({"iterate_history": [entry]}), encoding="utf-8")
    event = {"type": "work_completed", "adr_id": RUN, "affected_frs": ["FR-02.01"], "new_frs": []}
    (root / "shipwright_events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    return root, _commit(root)


def _py_base() -> dict[str, str]:
    return {".shipwright/planning/app/spec.md": _SPEC, "tests/test_a.py": _OLD}


def _catalog(*paths: str) -> dict[str, str]:
    return {CATALOG_PATH: json.dumps(list(paths))}


def test_a_marked_test_in_a_base_listed_file_passes_and_is_counted(tmp_path):
    root, head = _repo(tmp_path, {**_py_base(), **_catalog("tests/test_a.py")}, {"tests/test_a.py": _OLD + _MARKED})
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is True, result.detail
    assert "1 infrastructure-classed" in result.detail and "exempted 0 of 0" in result.detail


def test_without_a_catalog_at_base_the_absent_file_is_the_silent_empty_case(tmp_path):
    root, head = _repo(tmp_path, _py_base(), {"tests/test_a.py": _OLD + _MARKED})
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and not result.is_skipped
    assert "bad-infra-class" in result.detail and "earlier merge" in result.detail
    assert "cannot enforce" not in result.detail


def test_a_catalog_added_in_the_same_change_licenses_nothing(tmp_path):
    root, head = _repo(tmp_path, _py_base(), {"tests/test_a.py": _OLD + _MARKED, **_catalog("tests/test_a.py")})
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and "bad-infra-class" in result.detail
    assert "differs between the merge-base" in result.detail  # the warning survives a failing gate


def test_widening_the_catalog_in_the_change_does_not_cover_the_new_file(tmp_path):
    base = {**_py_base(), **_catalog("tests/test_a.py")}
    head = {"tests/test_b.py": "import pytest\n\n\n@pytest.mark.covers_none(\"infra\")\ndef test_b():\n    assert True\n",
            **_catalog("tests/test_a.py", "tests/test_b.py")}
    root, sha = _repo(tmp_path, base, head)
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is False and "tests/test_b.py::test_b" in result.detail and "bad-infra-class" in result.detail
    assert "differs between the merge-base" in result.detail


def test_a_malformed_catalog_at_base_grants_nothing(tmp_path):
    root, head = _repo(tmp_path, {**_py_base(), CATALOG_PATH: "{not json"}, {"tests/test_a.py": _OLD + _MARKED})
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and "bad-infra-class" in result.detail
    assert f"{CATALOG_PATH} is malformed" in result.detail


def test_a_wildcard_entry_grants_nothing(tmp_path):
    root, head = _repo(tmp_path, {**_py_base(), **_catalog("tests/*.py")}, {"tests/test_a.py": _OLD + _MARKED})
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and "bad-infra-class" in result.detail


def test_same_name_siblings_with_one_unmarked_stop(tmp_path):
    sibling = "\n\nclass TestB:\n    def test_probe(self):\n        assert True\n"
    root, head = _repo(tmp_path, {**_py_base(), **_catalog("tests/test_a.py")},
                       {"tests/test_a.py": _OLD + _MARKED + sibling})
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and "bad-infra-class" in result.detail


def test_marker_and_requirement_tag_together_stop(tmp_path):
    both = _MARKED.replace('@pytest.mark.covers_none("infra")', '@pytest.mark.covers("FR-02.01/AC01")\n@pytest.mark.covers_none("infra")')
    root, head = _repo(tmp_path, {**_py_base(), **_catalog("tests/test_a.py")}, {"tests/test_a.py": _OLD + both})
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and "bad-infra-class" in result.detail


def test_a_correction_warns_naming_the_dropped_tag_through_the_gate(tmp_path):
    real = '\n\nimport pytest\n\n\n@pytest.mark.covers("FR-02.01/AC01")\ndef test_real():\n    assert 2 == 2\n'
    tagged = '\n\nimport pytest\n\n\n@pytest.mark.covers("FR-02.01/AC01")\ndef test_probe():\n    assert True\n'
    base = {**_py_base(), **_catalog("tests/test_a.py")}
    base["tests/test_a.py"] = _OLD + tagged + real
    head = {"tests/test_a.py": _OLD + _MARKED + real}
    root, sha = _repo(tmp_path, base, head)
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.severity == "warning"  # passes with the correction warning, never silently
    assert "drops stand-in tag" in result.detail and "1 infrastructure-classed" in result.detail


def test_an_unreadable_base_catalog_cannot_enforce(tmp_path, monkeypatch):
    root, head = _repo(tmp_path, _py_base(), {"tests/test_a.py": _OLD + "\n\ndef test_other():\n    assert True\n"})
    real = gate.spec_text_at
    monkeypatch.setattr(gate, "spec_text_at", lambda r, sha, path: None if path == CATALOG_PATH else real(r, sha, path))
    result = gate.check_test_tag_binding(root, RUN, head)
    assert result.ok is False and result.detail.startswith("cannot enforce:") and CATALOG_PATH in result.detail
