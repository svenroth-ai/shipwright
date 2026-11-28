"""Unit P5: the public tag check (in-process) and the thin prose (F7)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from .test_release_p4_cli import VERSION
from .test_release_push_rule import _git

pytestmark = pytest.mark.covers("FR-01.09/AC01")

PLUGIN = Path(__file__).resolve().parents[1]
SKILL_DIR = PLUGIN / "skills" / "changelog"

# ---- the public tag check ------------------------------------------------------------------------------------

def _tag_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "tagrepo"
    repo.mkdir()
    (repo / "CHANGELOG.md").write_text(f"# Changelog\n\n## [v{VERSION}] - 2026-01-01\n\n- x\n", encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "x")
    _git(repo, "tag", f"v{VERSION}")
    return repo


def _load_script():
    script = PLUGIN / "scripts" / "checks" / "verify_release_tag.py"
    spec = importlib.util.spec_from_file_location("verify_release_tag_under_test", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # registered before exec
    spec.loader.exec_module(module)
    return script, module


def test_the_tag_check_script_main_uses_the_public_entry_in_process(tmp_path, capsys):
    """In-process (a subprocess shows no diff coverage): the script and the shared verifier meet only at ``check_release_tag``."""
    script, module = _load_script()
    assert not re.search(r"\bcc\._\w+", script.read_text(encoding="utf-8")), "the script reaches a private helper of the shared verifier"
    shared, repo = str(PLUGIN.parents[1] / "shared"), _tag_repo(tmp_path)
    base = ["--shared-root", shared, "--project-root", str(repo)]
    sys_path = list(sys.path)
    saved = {k: v for k, v in sys.modules.items() if k == "tools" or k.startswith("tools.") or k == "lib" or k.startswith("lib.")}
    try:
        for name in saved:
            del sys.modules[name]  # the shared verifiers import the shared `lib`, this plugin has one of its own
        assert module.main([*base, "--version", VERSION]) == 0
        found = json.loads(capsys.readouterr().out)
        assert found["ok"] and set(found["checks"]) == {"tag_exists", "changelog_names_release"} and "advisory" in found
        assert module.main([*base, "--version", "9.9.9"]) == 1
        assert not json.loads(capsys.readouterr().out)["checks"]["tag_exists"]["ok"]
    finally:
        for name in [k for k in sys.modules if k == "tools" or k.startswith("tools.") or k == "lib" or k.startswith("lib.")]:
            del sys.modules[name]
        sys.modules.update(saved)
        sys.path[:] = sys_path


# ---- the thin prose --------------------------------------------------------------------------------------------

def _prose() -> dict[str, str]:
    files = [SKILL_DIR / "SKILL.md", *sorted((SKILL_DIR / "references").glob("*.md"))]
    return {f.name: f.read_text(encoding="utf-8") for f in files if f.name != "release-notes-prompt.md"}  # the prompt is a runtime input, not prose for the model


def test_f7_no_prose_line_writes_run_state_in_any_mode():
    """Fails on the prose before P5: SKILL.md Step C and ``compliance-evidence.md`` named ``update-step`` and ``--restore``."""
    forbidden = ("update-step", "update_step", "--restore", "append_phase_history", "update_build_dashboard", "generate_session_handoff")
    found = {name: [w for w in forbidden if w in text] for name, text in _prose().items()}
    assert not {n: w for n, w in found.items() if w}, found


def test_f7_the_phase_close_is_one_close_phase_call_and_the_prose_has_no_history_or_aggregator_fences():
    skill = _prose()["SKILL.md"]
    assert len(re.findall(r'release\.py" close-phase', skill)) == 1 and "orchestrator.py" not in skill
    assert "aggregate_changelog.py" not in skill and "Since the file-per-iterate refactor" not in skill and "never type these" not in skill
    merge = "gh pr merge --{method} --match-head-commit {head} --delete-branch"  # U4: the line release.py merge-ready fills in
    assert re.findall(r"^gh pr merge .*$", skill, re.M) == [merge]  # outward commands stay literal


def test_the_prose_uses_one_word_for_who_waits_for_the_merge():
    skill, workflow = _prose()["SKILL.md"], _prose()["release-workflow.md"]
    assert "Guided mode" not in skill and "guided mode" not in workflow and "hand-invoked release" in skill and "hand-invoked release" in workflow

