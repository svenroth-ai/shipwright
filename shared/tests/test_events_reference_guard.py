"""Kill criterion 2 (issue 978, S3): no unclassified occurrence of the event log's name.

The reference-based guard (``lib/events_references.py``): every non-test file that names
``shipwright_events.jsonl`` or an alias must be registered with a tag, readers must use the
assembling reader, classifiers must list all three folders, and a new alias must not appear
unseen. Also pins the classifier behaviour itself (each one treats the folders as the log).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib import events_references as refs
from lib.events_log import ARCHIVE_DIR, DROPS_DIR, EVENT_FOLDERS, QUARANTINE_DIR, is_event_folder_path

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.covers("FR-01.11")


def test_kc2_no_unclassified_occurrence_of_the_event_log_name():
    assert refs.check(REPO) == []


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


def test_an_unregistered_file_is_unclassified(tmp_path):
    root = _repo(tmp_path, {"plugins/x/new.py": 'PATH = "shipwright_events.jsonl"\n'})
    problems = refs.check(root, {})
    assert any(p.startswith("UNCLASSIFIED: plugins/x/new.py") for p in problems)


def test_a_registered_file_that_stopped_mentioning_the_log_is_stale(tmp_path):
    root = _repo(tmp_path, {"plugins/x/old.py": "x = 1\n"})
    assert any(p.startswith("STALE: plugins/x/old.py") for p in refs.check(root, {"plugins/x/old.py": "R"}))


def test_a_reader_must_use_the_assembling_reader_and_a_classifier_must_list_the_folders(tmp_path):
    root = _repo(tmp_path, {
        "plugins/x/r.py": 'open("shipwright_events.jsonl")\n',
        "plugins/x/c.py": f'def p():\n    return ("shipwright_events.jsonl", "{DROPS_DIR}/")\n',
        "plugins/x/ok.py": f'def p():\n    return ("shipwright_events.jsonl", "{DROPS_DIR}", "{ARCHIVE_DIR}", "{QUARANTINE_DIR}")\n',
    })
    problems = refs.check(root, {"plugins/x/r.py": "R", "plugins/x/c.py": "C", "plugins/x/ok.py": "C"})
    assert any("r.py: tagged reader" in p for p in problems)
    assert any("c.py: tagged classifier" in p for p in problems)
    assert not any("ok.py" in p for p in problems)


def test_a_derived_module_level_alias_is_found_not_only_a_bare_constant(tmp_path):
    root = _repo(tmp_path, {"plugins/x/d.py": 'PATHS = ("a", "shipwright_events.jsonl")\nROOT = base / EVENT_FILE\n'})
    problems = refs.check(root, {"plugins/x/d.py": "M"})
    assert any("`PATHS` aliases" in p for p in problems) and any("`ROOT` aliases" in p for p in problems)


def test_an_alias_outside_the_known_set_and_a_renaming_import_are_found(tmp_path):
    root = _repo(tmp_path, {
        "plugins/x/a.py": 'MY_LOG = "shipwright_events.jsonl"\nfrom lib.events_log import resolve_events_path as rp\n',
    })
    problems = refs.check(root, {"plugins/x/a.py": "M"})
    assert any("`MY_LOG` aliases" in p for p in problems)
    assert any("renames an event-log alias" in p for p in problems)


def test_tests_and_artifacts_are_out_of_scope():
    assert not refs.scannable("plugins/x/tests/test_a.py")
    assert not refs.scannable("shared/scripts/lib/test_helper.py")
    assert not refs.scannable(".shipwright/agent_docs/architecture.md")
    assert refs.scannable("plugins/x/skills/y/SKILL.md")
    assert refs.scannable("shared/templates/gitattributes-union.template")


# --- the classifiers treat the folders as the log ---------------------------------------


@pytest.mark.parametrize("folder", EVENT_FOLDERS)
def test_every_classifier_knows_the_folder(folder):
    import importlib.util
    import sys

    from lib import churn_merge, gitattributes_union, gitignore_selfheal, project_root, review_diff_threshold, section_file_list
    from lib.change_type_paths import SHAPE_GENERIC, SHAPE_SHIPWRIGHT_MONOREPO, unclassified_paths

    assert is_event_folder_path(f"{folder}/x--aaaaaaaa--00000001.jsonl") and is_event_folder_path(f"./{folder}")
    assert not is_event_folder_path(f"{folder}-other/x") and not is_event_folder_path("src/.shipwright/events/drops")
    for shape in (SHAPE_GENERIC, SHAPE_SHIPWRIGHT_MONOREPO):
        assert unclassified_paths([f"{folder}/x--aaaaaaaa--00000001.jsonl"], "tooling", shape) == []
    assert not review_diff_threshold.is_counted_path(f"{folder}/x--aaaaaaaa--00000001.jsonl")
    assert any(f"{folder}/x".startswith(p) for p in section_file_list.FRAMEWORK_BOOKKEEPING)
    assert folder in project_root.CONFIG_MARKERS and folder in gitignore_selfheal.MANAGED_MARKER_PATHS
    assert churn_merge.classify([f"{folder}/x.jsonl"]) == ([], [f"{folder}/x.jsonl"])  # blocking: never auto-resolved
    assert folder in gitattributes_union.EVENT_FOLDERS_NO_UNION
    assert folder not in " ".join(gitattributes_union.ALL_MANAGED_PATHS)
    template = (REPO / gitattributes_union.TEMPLATE_PATH).read_text(encoding="utf-8")
    assert folder not in template, "a drop must never get a merge driver (it is ADD-only)"
    spec = importlib.util.spec_from_file_location(
        "_pr_review_generated_t", REPO / "plugins/shipwright-security/scripts/lib/pr_review_generated.py")
    gen = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gen
    spec.loader.exec_module(gen)
    assert gen.is_generated_path(f"{folder}/x--aaaaaaaa--00000001.jsonl")
    spec = importlib.util.spec_from_file_location(
        "_pr_review_skip_t", REPO / "plugins/shipwright-security/scripts/lib/pr_review_skip_safety.py")
    skip = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = skip
    spec.loader.exec_module(skip)
    assert not skip.is_safe_to_skip_review(f"{folder}/x--aaaaaaaa--00000001.jsonl"), "an event drop is a gate oracle"


def test_worktree_isolation_does_not_flag_event_folder_writes_as_a_leak():
    from lib import worktree_isolation as wi

    out = "".join(l + chr(10) for l in ("?? .shipwright/events/drops/", "?? .shipwright/events/drops/a--b--c.jsonl", "?? .shipwright/events/archive/f.jsonl", " M src/x.py"))
    paths, _ = wi._scan_porcelain(out)
    assert set(paths) == {"src/x.py"}


@pytest.mark.parametrize("rel,name", [
    ("plugins/shipwright-plan/scripts/checks/check-plan-gates.py", "PLAN_ALLOWED_PREFIXES"),
    ("plugins/shipwright-design/scripts/checks/check-design-gates.py", "DESIGN_ALLOWED_PREFIXES"),
])
def test_phase_boundary_gates_allow_the_event_folders(rel, name):
    import ast
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    (value,) = [n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == name for t in n.targets)]
    prefixes = {c.value for c in ast.walk(value) if isinstance(c, ast.Constant)}
    assert {f"{folder}/" for folder in EVENT_FOLDERS} <= prefixes
