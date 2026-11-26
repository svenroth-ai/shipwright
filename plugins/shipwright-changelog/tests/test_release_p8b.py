"""Unit P8b (operator re-scope 2026-11-25): Q5, Q7, Q8, Q10 and F9, each with a case the old code or prose fails.

Old behaviour, per decision: Q8 (D16) took ``v1.2.0`` as a version only to refuse it, accepted ``01.2.0`` and any version at
or below the last tag; Q7 (D9) offered ``--from vX`` (banner, ``SKILL.md``, guide, ``release.py prepare``) and built nothing
behind it; Q10 (D15) passed ``--body "## Changelog\\n\\n{entry}"`` so the PR showed a literal ``\\n`` and ``{entry}`` was
undefined; F9 wrote a cherry-picked bullet into the legacy ``[Unreleased]`` block, where it missed its release; Q5 (AC09) left
hand-written ``[Unreleased]`` entries out of the release. In-process with an injected runner, or on a real git repository.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import release
from lib import release_aggregate, release_pr_body, release_prepare, release_version
from lib.release_runner import CmdResult, Recorder

from .test_release_cli import SETUP, ok_runner, run_prepare

pytestmark = pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC04")

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
CHANGELOG = "# Changelog\n\n## [1.3.0] - 2026-11-25\n\n### Added\n\n- A new capability\n\n### Fixed\n\n- A defect\n\n## [1.2.0] - 2026-01-15\n\n- Old\n"


# ---- Q8 (D16): the version at the boundary --------------------------------------------------------------------

@pytest.mark.parametrize(("typed", "want"), [("v1.2.0", "1.2.0"), ("1.2.0", "1.2.0"), ("2.0.0-rc.1", "2.0.0-rc.1"), ("v0.1.0", "0.1.0")])
def test_a_leading_v_is_cut_off_so_the_tag_is_never_vv(typed, want):
    assert release._version(typed) == want
    assert f"v{release._version(typed)}" == f"v{want}"


@pytest.mark.parametrize("typed", ["1.2", "01.2.0", "1.2.0.0", "vv1.2.0", "1.2.0+build.5", "V1.2.0", "1.2.0-", "1.2.0-01", ""])
def test_anything_that_is_not_a_semver_number_is_refused_with_a_clear_error(typed):
    with pytest.raises(ValueError, match="is not a SemVer version"):
        release_version.normalize(typed)


def test_the_cli_refuses_an_invalid_version_as_a_usage_error(capsys):
    with pytest.raises(SystemExit) as stopped:
        release.main(["prepare", "--version", "1.2"])
    assert stopped.value.code == 2 and "is not a SemVer version" in capsys.readouterr().err


@pytest.mark.parametrize(("version", "last", "want"), [
    ("1.3.0", "v1.2.0", False), ("1.2.0", "v1.2.0", True), ("1.1.9", "v1.2.0", True), ("1.2.0", "v1.2.0-rc.1", False),
    ("1.2.0-rc.2", "v1.2.0-rc.10", True), ("1.2.0-rc.1", "v1.2.0-beta", False), ("1.2.0-1", "v1.2.0-alpha", True),
    ("0.1.0", None, False), ("1.0.0", "release-2024", None)])
def test_not_above_follows_semver_precedence(version, last, want):
    assert release_version.not_above(version, last) is want


@pytest.mark.parametrize("version", ["1.2.0", "1.1.0"])
def test_prepare_refuses_a_version_that_is_not_higher_than_the_last_tag(tmp_path, plugin_root, version):
    code, out = run_prepare(tmp_path, plugin_root, ok_runner(), version=version)
    assert (code, out["status"], out["reason"]) == (2, "stop", "version_not_above_last_tag")
    assert SETUP["last_tag"] in out["message"] and version in out["message"]


def test_prepare_takes_a_higher_version_and_notes_a_last_tag_it_cannot_compare(tmp_path, plugin_root):
    code, out = run_prepare(tmp_path, plugin_root, ok_runner(), version="1.4.0")
    assert (code, out["version"]) == (0, "1.4.0")
    # v01.2.0 has the release-tag shape git_utils and `git tag --merged HEAD` both emit, but is no SemVer number
    odd = ok_runner(setup={"stdout": json.dumps({**SETUP, "last_tag": "v01.2.0"})}, **{"tags-merged": {"stdout": "v01.2.0\n"}})
    (tmp_path / "odd").mkdir()
    code, out = run_prepare(tmp_path / "odd", plugin_root, odd, version="1.4.0")
    assert code == 0 and any("v01.2.0 are no SemVer version" in n for n in out["notices"])


# ---- Q7 (D9): no `--from` anywhere -----------------------------------------------------------------------------

def test_from_is_offered_nowhere_and_passing_it_is_refused(capsys):
    skill = (PLUGIN / "skills" / "changelog" / "SKILL.md").read_text(encoding="utf-8")
    guide = (REPO / "docs" / "guide.md").read_text(encoding="utf-8")
    assert "--from" not in skill and "--from" not in release_prepare.BANNER and "--from" not in (PLUGIN / "scripts" / "release.py").read_text(encoding="utf-8")
    assert "/shipwright-changelog --from" not in guide
    with pytest.raises(SystemExit) as stopped:
        release.main(["prepare", "--from", "v0.1.0"])
    assert stopped.value.code == 2 and "unrecognized arguments: --from" in capsys.readouterr().err


# ---- Q10 (D15): the PR body from a file ------------------------------------------------------------------------

def test_the_pr_body_file_has_real_newlines_and_this_versions_section(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    code, out = release_pr_body.pr_body(Recorder(lambda *a, **k: None, tmp_path), version="1.3.0")
    body = Path(out["body_file"]).read_text(encoding="utf-8")
    assert code == 0 and out["title"] == "Release v1.3.0" and "\\n" not in body
    assert body == "## Changelog\n\n## [1.3.0] - 2026-11-25\n\n### Added\n\n- A new capability\n\n### Fixed\n\n- A defect\n"
    assert subprocess.run(["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True).stdout.strip() == "?? CHANGELOG.md"


@pytest.mark.parametrize(("text", "reason"), [(CHANGELOG.replace("1.3.0", "1.2.9"), "section_missing"),
                                              (CHANGELOG + "\n## [1.3.0] - 2026-11-20\n\n- Twice\n", "section_ambiguous")])
def test_a_body_with_no_or_two_sections_is_refused_never_guessed(tmp_path, text, reason):
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    code, out = release_pr_body.pr_body(Recorder(lambda *a, **k: None, tmp_path), version="1.3.0")
    assert (code, out["status"], out["reason"]) == (1, "refused", reason) and "body_file" not in out


def test_the_skill_passes_the_body_from_a_file_and_keeps_the_title():
    skill = (PLUGIN / "skills" / "changelog" / "SKILL.md").read_text(encoding="utf-8")
    assert '--body-file "{body_file}"' in skill and '--title "Release v{version}"' in skill
    assert '--body "' not in skill and 'release.py" pr-body' in skill
    assert skill.index('release.py" pr-body') < skill.index("gh pr create")


# ---- F9 and Q5: what `aggregate` hands the tools ---------------------------------------------------------------

def _aggregate(tmp_path, **kw):
    calls: list[tuple[str, list[str]]] = []

    def fake(key, argv, cwd, **_opts):
        calls.append((key, list(argv)))
        out = '{"version": "1.3.0", "section_preview": "P", "hand_written_entries": [{"category": "Added", "text": "H"}]}'
        return CmdResult(key, tuple(argv), 1 if key == "tag-check" else 0, out if key.startswith("aggregate") else "")
    code, out = release_aggregate.aggregate(Recorder(fake, tmp_path), PLUGIN, version="1.3.0", **kw)
    return calls, out


def test_f9_a_cherry_picked_bullet_is_written_as_a_drop_not_into_unreleased(tmp_path):
    calls, out = _aggregate(tmp_path, fallback_entries=[("Fixed", "A cherry-picked fix")])
    argv = next(a for k, a in calls if k == "fallback-append")
    assert Path(argv[2]).name == "write_changelog_drop.py" and "append_changelog_entry.py" not in " ".join(argv)
    assert argv[argv.index("--category") + 1] == "Fixed" and argv[argv.index("--bullet") + 1] == "A cherry-picked fix"
    assert [k for k, _ in calls].index("fallback-append") < [k for k, _ in calls].index("aggregate")


@pytest.mark.parametrize("dry_run", [True, False])
def test_q5_both_aggregate_calls_move_the_hand_written_entries_and_only_the_preview_marks_them(tmp_path, dry_run):
    calls, out = _aggregate(tmp_path, dry_run=dry_run)
    argv = next(a for k, a in calls if k.startswith("aggregate"))
    assert "--move-unreleased" in argv and out["hand_written"] == [{"category": "Added", "text": "H"}]
    assert ("section_preview" in out) is dry_run


# ---- review round: build metadata on a tag, ASCII digits, a library caller ------------------------------------

@pytest.mark.parametrize(("version", "last", "want"), [("1.9.0", "v2.0.0+build.5", True), ("2.0.1", "v2.0.0+build.5", False),
                                                       ("2.0.0", "v2.0.0+b", True)])
def test_a_tags_build_metadata_is_ignored_for_the_order(version, last, want):
    assert release_version.not_above(version, last) is want


@pytest.mark.parametrize("typed", ["1.\u0662.0", "\u0661.2.0", "1.2.0-rc.\u0663"])
def test_non_ascii_digits_are_refused(typed):
    with pytest.raises(ValueError, match="is not a SemVer version"):
        release_version.normalize(typed)


def test_prepare_as_a_library_takes_a_raw_v_version(tmp_path, plugin_root):
    code, out = run_prepare(tmp_path, plugin_root, ok_runner(), version="v1.4.0")
    assert (code, out.get("version")) == (0, "1.4.0")


def test_prepare_as_a_library_refuses_a_raw_non_semver_version_without_raising(tmp_path, plugin_root):
    code, out = run_prepare(tmp_path, plugin_root, ok_runner(), version="1.4")
    assert (code, out["reason"]) == (2, "invalid_version")
