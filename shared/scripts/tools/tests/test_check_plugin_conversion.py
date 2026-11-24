"""check_plugin_conversion.py: a converted plugin stays converted (programme Tz, pilot unit P7).

Each seeded regression builds a throwaway tree that is clean except for one fault, so a failure names it. The real
registry runs against the real changelog tree once: what P3 to P6 delivered must pass. Everything runs in-process.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools: the module imports its sibling by bare name

import check_plugin_conversion as cpc  # noqa: E402
import junit_promises as jp  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.09")  # the conversion check of the changelog pilot; no AC is claimed

REPO = Path(__file__).resolve().parents[4]
B_TEXT = {  # what each B-item pattern needs to find
    "A2+": '"gates"', "A3+": "def check():\n", "A6+": "def save():\n", "A9+": "def summary():\n",
    "B1": "release_state.json", "B2": "release_guard.py", "B2+": "release_state", "B4": "release_verify.verify(x)",
}
OFFENDERS = {  # one line per A-item that must trip it (prose scope: placed in a reference)
    "A1": "uv run setup-changelog.py --x", "A2": "**Autonomous mode**: skip", "A3": "Read docs/migrations first",
    "A4": "pass --fail-if-empty", "A5": "call orchestrator.py update-step", "A6": "pass --release-date 2026-01-01",
    "A9": "Commits: {N} categorized", "A10": "git tag -a v1.0.0",
}
PROMISES = {"subject": "p", "schema": 1, "promises": [
    {"id": "X/AC01", "status": "passing", "check": {"kind": "test", "id": "plugins/p/tests/test_x.py::test_a"}},
    {"id": "X/AC02", "status": "gap", "check": None}]}


def entry() -> dict:
    return cpc.load_entry("shipwright-changelog")


def build_tree(root: Path, skill_extra: str = "", reference: str = "", drop: str | None = None) -> dict:
    ent = entry()
    calls = "\n".join(f'uv run "{{plugin_root}}/scripts/release.py" {sub} --x' for sub in ent["subcommands"])
    files = {ent["skill"]: f"# Skill\n{calls}\n{skill_extra}\n", ent["references"] + "/ref.md": f"Prose.\n{reference}\n",
             ent["cli"]: "# cli\n", ent["promise_list"]: json.dumps(PROMISES)}
    for item in ent["b_items"]:
        files[item["file"]] = files.get(item["file"], "") + B_TEXT[item["id"]] + "\n"
    files[ent["export"]] = jp.dump(jp.export_trace(PROMISES))
    for rel, text in files.items():
        if rel != drop:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
    return ent


def problems(root: Path, ent: dict) -> list[str]:
    return cpc.check_prose(root, ent) + cpc.check_code(root, ent) + cpc.check_export(root, ent)


def test_a_clean_tree_passes(tmp_path):
    assert problems(tmp_path, build_tree(tmp_path)) == []


@pytest.mark.parametrize("item_id", sorted(OFFENDERS))
def test_an_a_item_back_in_the_skill_prose_is_caught(tmp_path, item_id):
    found = problems(tmp_path, build_tree(tmp_path, skill_extra=OFFENDERS[item_id]))
    assert [p for p in found if p.startswith(item_id + ":")], found


def test_the_old_prose_mechanic_in_a_reference_is_caught_only_for_prose_scope(tmp_path):
    found = problems(tmp_path, build_tree(tmp_path, reference="call orchestrator.py update-step\nsetup-changelog.py"))
    assert [p for p in found if p.startswith("A5:") and "ref.md" in p] and not [p for p in found if p.startswith("A1:")]


@pytest.mark.parametrize("item", entry()["b_items"], ids=lambda i: i["id"])
def test_a_missing_b_item_is_caught(tmp_path, item):
    ent = build_tree(tmp_path)
    (tmp_path / item["file"]).write_text("nothing here\n", encoding="utf-8")
    found = problems(tmp_path, ent)
    assert [p for p in found if p.startswith(item["id"] + ":")], found


def test_a_subcommand_the_prose_never_calls_and_a_missing_cli_are_caught(tmp_path):
    ent = build_tree(tmp_path)
    skill = tmp_path / ent["skill"]
    skill.write_text(skill.read_text(encoding="utf-8").replace("push-tag", "push"), encoding="utf-8")
    (tmp_path / ent["cli"]).unlink()
    found = cpc.check_code(tmp_path, ent)
    assert any("never calls `release.py push-tag`" in p for p in found) and any("does not exist" in p for p in found)


def test_a_stale_export_is_caught(tmp_path):
    ent = build_tree(tmp_path)
    (tmp_path / ent["export"]).write_text("{}\n", encoding="utf-8")
    assert any("differs from the promise list" in p for p in cpc.check_export(tmp_path, ent))


def test_an_unreadable_file_or_registry_is_exit_2_material(tmp_path):
    ent = build_tree(tmp_path, drop=entry()["b_items"][0]["file"])
    with pytest.raises(cpc.ConversionError, match="cannot be read"):
        cpc.check_code(tmp_path, ent)
    with pytest.raises(cpc.ConversionError, match="no readable entry"):
        cpc.load_entry("nope")
    bad = {**entry(), "a_items": [{"id": "Z", "scope": "skill", "forbidden": "(", "why": "x"}]}
    build_tree(tmp_path)
    with pytest.raises(cpc.ConversionError, match="not a regex"):
        cpc.check_prose(tmp_path, bad)


def test_the_real_changelog_tree_is_converted():
    ent = entry()
    assert problems(REPO, ent) == []


def test_the_codex_bundle_resolves_the_cli_and_every_cited_script(tmp_path):
    assert cpc.check_bundle(REPO, entry()) == []  # the real build, and the CLI really starts from the bundle copy


def _fake_build(skip: str | None = None, keep_cli: bool = True):
    """A bundle that holds the CLI, the skill copy and every script the real SKILL.md cites, minus ``skip``."""
    cited = cpc.CITED.findall((REPO / entry()["skill"]).read_text(encoding="utf-8"))
    wanted = {"skills/changelog/SKILL.md", "origin/shipwright-changelog/scripts/release.py"}
    wanted |= {("origin/shipwright-changelog/" if which == "plugin_root" else "shared/") + rel for which, rel in cited}

    def build(project_root, out_dir):
        for rel in wanted - {skip}:
            if keep_cli or not rel.endswith("release.py"):
                (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                (out_dir / rel).write_text("x", encoding="utf-8")
    return build


OK = lambda *a, **k: SimpleNamespace(returncode=0, stderr="")  # noqa: E731


def test_a_bundle_without_the_cli_a_skill_copy_or_a_cited_script_is_caught():
    assert cpc.check_bundle(REPO, entry(), build=_fake_build(), run=OK) == []
    assert any("release.py is missing" in p for p in cpc.check_bundle(REPO, entry(), build=_fake_build(keep_cli=False), run=OK))
    assert any("SKILL.md is missing" in p for p in cpc.check_bundle(REPO, entry(), build=_fake_build("skills/changelog/SKILL.md"), run=OK))
    gone = "shared/scripts/tools/publish_release_notes.py"
    assert any("publish_release_notes.py" in p and "does not hold" in p for p in cpc.check_bundle(REPO, entry(), build=_fake_build(gone), run=OK))


def test_a_cli_that_does_not_start_in_the_bundle_is_caught():
    boom = lambda *a, **k: SimpleNamespace(returncode=3, stderr="ImportError: lib")  # noqa: E731
    assert any("exits 3" in p and "ImportError" in p for p in cpc.check_bundle(REPO, entry(), build=_fake_build(), run=boom))


def test_verify_local_red_is_a_finding_and_green_is_not():
    assert cpc.check_verify_local(REPO, run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="")) == []
    red = cpc.check_verify_local(REPO, run=lambda *a, **k: SimpleNamespace(returncode=1, stdout="gate X failed"))
    assert red and "gate X failed" in red[0]


def _junit(path: Path, cases: list[tuple[str, str, str]]) -> Path:
    body = "".join(f'<testcase classname="{c}" name="{n}">{extra}</testcase>' for c, n, extra in cases)
    path.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>", encoding="utf-8")
    return path


def test_main_runs_the_static_checks_the_report_and_writes_the_export(tmp_path, capsys, monkeypatch):
    ent = build_tree(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"plugins": [{**ent, "sentinel": {"file": "plugins/p/tests/test_freeze.py", "name": "test_freeze"},
                                                 "seeded": ["plugins/p/tests/test_seed.py::test_seed"]}]}), encoding="utf-8")
    base = ["--project-root", str(tmp_path), "--plugin", "shipwright-changelog", "--registry", str(registry)]
    assert cpc.main(base) == 0 and "converted" in capsys.readouterr().out
    green = [("tests.test_x", "test_a", ""), ("tests.test_freeze", "test_freeze", ""), ("tests.test_seed", "test_seed", "")]
    assert cpc.main([*base, "--junit", str(_junit(tmp_path / "ok.xml", green)), "--write-export"]) == 0
    skipped = [("tests.test_x", "test_a", "<skipped/>"), *green[1:]]
    assert cpc.main([*base, "--junit", str(_junit(tmp_path / "bad.xml", skipped))]) == 1
    assert "reads passing, but its test skipped" in capsys.readouterr().out
    assert cpc.main([*base, "--junit", str(tmp_path / "missing.xml")]) == 2
    assert cpc.main([*base, "--plugin", "nope"]) == 2
    monkeypatch.setattr(cpc, "check_verify_local", lambda root: ["verify_local: red"])
    assert cpc.main([*base, "--verify-local"]) == 1


def test_a_hanging_cli_or_verify_run_is_a_finding_not_a_traceback():
    import subprocess

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("x", 1)
    assert any("did not answer" in p for p in cpc.check_bundle(REPO, entry(), build=_fake_build(), run=hang))
    assert "did not finish" in cpc.check_verify_local(REPO, run=hang)[0]
