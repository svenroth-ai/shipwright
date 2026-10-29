"""Package intake runs the Project content check and warns on thin visual guidelines (E4, finding F6).

In-process wherever possible: the diff-coverage gate cannot see a subprocess.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))

from _brief_dir_helpers import DEFAULT_MD, build_package  # noqa: E402
import brief_dir_intake as bdi  # noqa: E402
import tools.brief_project_mode as bpm  # noqa: E402

checks = bdi._lib("brief_intake_checks")
REPO = Path(__file__).resolve().parents[2]
KIT_TOKENS = REPO / "plugins" / "shipwright-design" / "skills" / "design" / "kit" / "untitled-ui" / "tokens"
THIN_MD = DEFAULT_MD.replace("- Purpose: keep ideas from getting lost\n", "- Purpose:\n")  # the F6 shape: an empty dimension


def _set(tmp_path: Path, name: str = "warm") -> str:
    """A shipped token set written as `--token: value;` lines (a complete, passing declaration)."""
    return "\n".join(l.strip() for l in (KIT_TOKENS / f"{name}.css").read_text(encoding="utf-8").splitlines()
                     if l.strip().startswith("--"))


@pytest.fixture(scope="module")
def kit():
    mod = checks._kit_checker()
    assert mod is not None, "the design plugin's check_brand_tokens.py sits next to shared in the repo"
    return mod


@pytest.mark.covers("FR-01.02")
def test_intake_refuses_the_content_the_project_phase_would_refuse(tmp_path):
    build_package(tmp_path, THIN_MD)
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir("brief", tmp_path)
    assert exc.value.code == "invalid_content"
    assert [i["code"] for i in exc.value.issues] == ["empty_dimension"]
    assert exc.value.issues[0]["capability"] == "Capture note"


@pytest.mark.covers("FR-01.02")
def test_intake_and_project_phase_share_one_check(tmp_path):
    build_package(tmp_path, THIN_MD)
    write_issues = checks.check_content(tmp_path, "brief")
    assert write_issues == bpm.content_issues(THIN_MD)[2]  # same function, same answer, no second rule set


@pytest.mark.covers("FR-01.02")
def test_valid_content_passes_and_carries_warnings(tmp_path):
    build_package(tmp_path)
    out = bdi.intake_dir("brief", tmp_path)
    assert out["source"] == "package" and isinstance(out["warnings"], list)
    assert checks.check_content(tmp_path, "brief") == []


@pytest.mark.covers("FR-01.02")
def test_content_check_that_cannot_run_is_an_error_not_a_pass(tmp_path):
    with pytest.raises(RuntimeError, match="did not run"):
        checks.check_content(tmp_path, "no-such-dir")  # the tool reports a refusal, not a result
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir("brief", tmp_path)
    assert exc.value.code == "bad_brief_dir"


@pytest.mark.covers("FR-01.02")
def test_check_command_is_read_only_and_exits_by_result(tmp_path, capsys):
    build_package(tmp_path, THIN_MD)
    before = sorted(p.name for p in tmp_path.iterdir())
    assert bpm.main(["check", "--project-root", str(tmp_path), "--brief-dir", "brief"]) == 1
    assert '"empty_dimension"' in capsys.readouterr().out
    build_package(tmp_path)
    assert bpm.main(["check", "--project-root", str(tmp_path), "--brief-dir", "brief"]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == before  # nothing written


@pytest.mark.covers("FR-01.02")
def test_complete_token_set_has_no_warnings(tmp_path, kit):
    g = tmp_path / "visual-guidelines.md"
    g.write_text("# Visual\n\n```css\n:root {\n" + _set(tmp_path) + "\n}\n```\n", encoding="utf-8")
    assert checks.token_warnings(g, kit) == []


@pytest.mark.covers("FR-01.02")
def test_prose_guidelines_name_the_missing_kit_tokens(tmp_path, kit):
    g = tmp_path / "visual-guidelines.md"
    g.write_text("## Colours\n- Background #f6f7f9, text #111827\n- `--color-bg: #f6f7f9` and --color-text: #111827;\n",
                 encoding="utf-8")
    out = checks.token_warnings(g, kit)
    missing = next(w for w in out if "kit colour tokens" in w)
    assert "declares 2 of the" in missing and "--color-primary" in missing and "--color-bg," not in missing
    assert len(out) == 1  # declaring two tokens over the shipped base set breaks no contract rule


@pytest.mark.covers("FR-01.02")
def test_weak_contrast_and_small_text_are_named_with_a_fix(tmp_path, kit):
    css = _set(tmp_path).replace("--color-muted:", "--color-muted-unused:")
    css += "\n--color-muted: #cccccc;\n--font-size-base: 12px;\n--color-focus: rgb(1, 2, 3);"
    g = tmp_path / "g.md"
    g.write_text(css, encoding="utf-8")
    out = checks.token_warnings(g, kit)
    assert any(w.startswith("g.md: muted #cccccc on bg") and "< 7.0; try --color-muted: #" in w for w in out)
    assert any("font sizes below the minimum" in w for w in out)
    assert any("--color-focus" in w and "not a solid hex colour" in w for w in out)


@pytest.mark.covers("FR-01.02")
def test_a_failing_background_pair_moves_the_fill(tmp_path, kit):
    g = tmp_path / "g.md"
    g.write_text("--color-on-primary: #eeeeee; --color-primary: #dddddd;\n", encoding="utf-8")
    assert any("try --color-primary: #" in w for w in checks.token_warnings(g, kit))


@pytest.mark.covers("FR-01.02")
def test_missing_or_unreadable_guidelines_still_warn(tmp_path, kit):
    out = checks.token_warnings(tmp_path / "absent.md", kit)
    assert any("declares 0 of the" in w for w in out)  # an absent file is a package problem elsewhere; here: no tokens
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe\x00\xd8")
    assert "could not be read" in checks.token_warnings(bad, kit)[0]


@pytest.mark.covers("FR-01.02")
def test_missing_kit_skips_the_check_and_says_so(tmp_path, monkeypatch):
    assert checks._kit_checker(tmp_path) is None
    monkeypatch.setattr(checks, "_kit_checker", lambda root=None: None)
    out = checks.token_warnings(tmp_path / "g.md")
    assert len(out) == 1 and "skipped" in out[0]


@pytest.mark.covers("FR-01.02")
def test_kit_checker_is_found_in_the_cache_layout_newest_version(tmp_path):
    rel = Path("scripts") / "tools" / "check_brand_tokens.py"
    for ver, marker in (("0.2.1", "OLD"), ("0.10.0", "NEW")):  # 0.10.0 is newer than 0.2.1 (not a string sort)
        f = tmp_path / "shipwright-design" / ver / rel
        f.parent.mkdir(parents=True)
        f.write_text(f"MARK = {marker!r}\n", encoding="utf-8")
    assert checks._kit_checker(tmp_path).MARK == "NEW"


@pytest.mark.covers("FR-01.02")
def test_kit_checker_that_fails_to_load_is_not_swallowed(tmp_path):
    f = tmp_path / "plugins" / "shipwright-design" / "scripts" / "tools" / "check_brand_tokens.py"
    f.parent.mkdir(parents=True)
    f.write_text("raise ValueError('broken')\n", encoding="utf-8")
    with pytest.raises(ValueError, match="broken"):
        checks._kit_checker(tmp_path)
    assert "_shipwright_kit_check_brand_tokens" not in sys.modules


@pytest.mark.covers("FR-01.02")
def test_a_check_that_hangs_is_an_error_distinct_from_invalid_content(tmp_path, monkeypatch):
    def hang(*a, **kw):
        raise checks.subprocess.TimeoutExpired("x", 1)
    monkeypatch.setattr(checks.subprocess, "run", hang)
    build_package(tmp_path)
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir("brief", tmp_path)
    assert exc.value.code == "io_error" and "did not run" in exc.value.message


@pytest.mark.covers("FR-01.02")
def test_a_rule_outside_the_pair_list_is_judged_by_the_same_kit_entry_point(tmp_path, kit):
    g = tmp_path / "g.md"
    g.write_text("--color-primary: #1d4ed8; --color-primary-hover: #93b4ff;\n", encoding="utf-8")  # hover lighter than primary
    assert any("primary-hover" in w and "must be darker" in w for w in checks.token_warnings(g, kit))


@pytest.mark.covers("FR-01.02")
def test_a_kit_checker_that_breaks_becomes_a_warning_never_an_exception(tmp_path):
    class Broken:
        def parse_colours(self, css):
            raise AttributeError("renamed in the kit")

        CONTRAST_PAIRS, OTHER_COLOURS = [], ()
    out = checks.token_warnings(tmp_path / "g.md", Broken())
    assert out == ["kit token check could not run: AttributeError: renamed in the kit"]


@pytest.mark.covers("FR-01.02")
def test_installed_version_wins_over_the_plugins_mirror(tmp_path):
    rel = Path("scripts") / "tools" / "check_brand_tokens.py"
    for where, marker in ((tmp_path / "plugins" / "shipwright-design", "MIRROR"), (tmp_path / "shipwright-design" / "0.3.0", "INSTALLED")):
        f = where / rel
        f.parent.mkdir(parents=True)
        f.write_text(f"MARK = {marker!r}" + chr(10), encoding="utf-8")
    assert checks._kit_checker(tmp_path).MARK == "INSTALLED"


@pytest.mark.covers("FR-01.02")
def test_a_kit_that_fails_to_load_only_warns_at_the_token_check(tmp_path, monkeypatch):
    def boom(root=None):
        raise ImportError("old kit")
    monkeypatch.setattr(checks, "_kit_checker", boom)
    assert checks.token_warnings(tmp_path / "g.md") == ["kit token check could not run: ImportError: old kit"]


@pytest.mark.covers("FR-01.02")
def test_the_kit_surface_intake_depends_on_exists(kit):
    for name in ("parse_colours", "parse_sizes", "unreadable_values", "check", "CONTRAST_PAIRS", "OTHER_COLOURS", "KIT"):
        assert hasattr(kit, name), f"check_brand_tokens.{name} is used by brief_intake_checks"
    assert (kit.KIT / "tokens" / "warm.css").is_file()
