"""An explicit stack profile in a wizard brief wins over inference and is resolver-checked
(campaign brief-driven-run, B2b)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

import brief_dir_intake as bdi  # noqa: E402
import brief_intake  # noqa: E402

LIB = Path(brief_intake.__file__).resolve()
BASE = {"description": "A booking tool", "users": "public", "persistence": "yes", "run_location": "web"}
WEBUI_LINE = ("A booking tool (Intake — Users: Customers / public; Saves data: Yes; Runs: On the web; "
              "Stack profile: {name}; Supabase env vars will be needed at the Deploy step (not before).)")

pytestmark = pytest.mark.covers("FR-01.01")


@pytest.fixture(autouse=True)
def _user_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_USER_PROFILES_DIR", str(tmp_path / "user-profiles"))
    return tmp_path / "user-profiles"


def _write(directory: Path, name: str, **extra) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps({"name": name, "description": f"custom {name}", **extra}), encoding="utf-8")


def test_explicit_profile_wins_over_inference_and_is_passed_on(tmp_path):
    out = brief_intake.intake({**BASE, "profile": "vite-hono"}, str(tmp_path))  # persistence=yes would infer supabase
    assert out["profile"] == "vite-hono"
    assert out["profile_source"] == "bundled" and out["profile_requested"] == "vite-hono"
    assert "explicit" in out["profile_reason"]
    assert out["env_questions"] == []  # follows the CHOSEN profile, not the inferred one
    assert "profile_error" not in out


def test_explicit_supabase_profile_asks_the_env_questions(tmp_path):
    out = brief_intake.intake({**BASE, "persistence": "no", "profile": "supabase-nextjs"}, str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and out["env_questions"]


def test_unknown_name_is_reported_not_replaced(tmp_path):
    out = brief_intake.intake({**BASE, "profile": "no-such-stack"}, str(tmp_path))
    assert out["profile"] is None  # NOT supabase-nextjs (the inference) and not silent
    assert out["profile_requested"] == "no-such-stack"
    assert out["profile_error"]["code"] == "not_found"
    assert out["warnings"] and "no-such-stack" in out["warnings"][0]


@pytest.mark.parametrize("bad", ["../etc/passwd", "Vite-Hono", 7, ["vite-hono"]])
def test_invalid_names_are_reported(tmp_path, bad):
    out = brief_intake.intake({**BASE, "profile": bad}, str(tmp_path))
    assert out["profile"] is None and out["profile_error"]["code"] in ("invalid", "not_found")


def test_no_profile_in_the_brief_behaves_as_before(tmp_path):
    out = brief_intake.intake(dict(BASE), str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and "profile_error" not in out and "warnings" not in out
    blank = brief_intake.intake({**BASE, "profile": "  "}, str(tmp_path))
    assert blank == out


def test_project_and_user_profiles_resolve_like_bundled(tmp_path, _user_dir):
    _write(_user_dir, "my-user-stack")
    _write(tmp_path / ".shipwright" / "profiles", "my-project-stack")
    user = brief_intake.intake({**BASE, "profile": "my-user-stack"}, str(tmp_path))
    proj = brief_intake.intake({**BASE, "profile": "my-project-stack"}, str(tmp_path))
    assert (user["profile"], user["profile_source"]) == ("my-user-stack", "user")
    assert (proj["profile"], proj["profile_source"]) == ("my-project-stack", "project")
    assert brief_intake.intake({**BASE, "profile": "my-project-stack"}, str(tmp_path / "elsewhere"))["profile_error"]


def test_profile_file_contents_are_untrusted(tmp_path):
    pdir = tmp_path / ".shipwright" / "profiles"
    pdir.mkdir(parents=True)
    (pdir / "evil.json").write_text('{"name": "evil", "x": "\x1b[31mRED', encoding="utf-8")  # truncated JSON, ESC byte
    out = brief_intake.intake({**BASE, "profile": "evil"}, str(tmp_path))
    assert out["profile"] is None and out["profile_error"]["code"] == "invalid"
    assert out["refused"] is True and out["code"] == "profile_unusable"  # same shape as a package refusal (exit 3)
    assert not any(ord(c) < 32 for c in out["profile_error"]["message"])  # control characters never reach the output


def test_webui_one_line_trailer_and_text_keys(tmp_path):
    out = brief_intake.intake(WEBUI_LINE.format(name="vite-hono"), str(tmp_path))
    assert out["profile"] == "vite-hono" and out["profile_source"] == "bundled"
    assert brief_intake.intake("description: x\nStack profile: vite-hono", str(tmp_path))["profile"] == "vite-hono"
    fenced = '```json\n{"description": "x", "stack_profile": "vite-hono"}\n```'
    assert brief_intake.intake(fenced, str(tmp_path))["profile"] == "vite-hono"
    gone = brief_intake.intake(WEBUI_LINE.format(name="gone-stack"), str(tmp_path))
    assert gone["profile"] is None and gone["profile_requested"] == "gone-stack"
    plain = brief_intake.intake("I want a Stack profile: foo kind of app (Intake is nice)", str(tmp_path))  # prose, no key line, no trailer
    assert "profile_requested" not in plain


def test_cli_exits_3_on_an_unusable_profile_and_0_otherwise(tmp_path):
    brief = tmp_path / "brief.json"

    def run():
        return subprocess.run([sys.executable, str(LIB), "--brief", str(brief), "--project-root", str(tmp_path)],
                              capture_output=True, text=True)

    brief.write_text(json.dumps({**BASE, "profile": "vite-hono"}), encoding="utf-8")
    ok = run()
    assert ok.returncode == 0 and json.loads(ok.stdout)["profile"] == "vite-hono"
    brief.write_text(json.dumps({**BASE, "profile": "nope"}), encoding="utf-8")
    bad = run()
    assert bad.returncode == 3 and json.loads(bad.stdout)["profile_error"]["code"] == "not_found"


def test_fixture_refusal_says_only_the_operator_sets_the_switch():
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.check_approval({"approved_by": "fixture:x", "approved_at": "2026-10-25"}, env={})
    msg = exc.value.message
    assert "only the OPERATOR may set" in msg and "NEVER set it" in msg and "report this refusal" in msg


def test_field_precedence_and_blank_values(tmp_path):
    both = brief_intake.intake({**BASE, "profile": "vite-hono", "stack_profile": "supabase-nextjs"}, str(tmp_path))
    assert both["profile"] == "vite-hono"  # `profile` wins over its alias
    blank_with_trailer = {**BASE, "profile": "", "description": WEBUI_LINE.format(name="vite-hono")}
    out = brief_intake.intake(blank_with_trailer, str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and "profile_requested" not in out  # blank: trailer not consulted
    idea = "Stack profile: nope is my idea " + WEBUI_LINE.format(name="vite-hono").replace("; Stack profile: vite-hono", "; Stack profile: vite-hono; Stack profile: x")
    ambiguous = brief_intake.intake({**BASE, "description": idea}, str(tmp_path))  # two items: refused, not guessed
    assert ambiguous["profile"] is None and ambiguous["code"] == "profile_unusable"
    dotted = brief_intake.intake(WEBUI_LINE.format(name="a.b"), str(tmp_path))
    assert dotted["profile"] is None and dotted["profile_error"]["code"] in ("invalid", "not_found")


def test_text_stack_profile_key_beats_a_bare_profile_hint_in_either_order(tmp_path):
    for text in ("description: x\nprofile: vite-hono\nstack_profile: supabase-nextjs",
                 "description: x\nstack_profile: supabase-nextjs\nprofile: vite-hono"):
        assert brief_intake.intake(text, str(tmp_path))["profile"] == "supabase-nextjs"
    blank_then_alias = brief_intake.intake({**BASE, "profile": "", "stack_profile": "vite-hono"}, str(tmp_path))
    assert blank_then_alias["profile"] == "vite-hono"  # a blank field does not hide a populated alias


def test_trailer_item_is_validated_whole_not_by_its_first_word(tmp_path):
    out = brief_intake.intake(WEBUI_LINE.format(name="vite-hono invalid"), str(tmp_path))
    assert out["profile"] is None and out["profile_requested"] == "vite-hono invalid"


def test_free_text_profile_line_stays_in_the_description(tmp_path):
    out = brief_intake.intake("Profile: a SaaS for dentists", str(tmp_path))
    assert "profile_requested" not in out and out["profile"] is None  # not a name shape: no refusal
    assert "dentists" in (out["brief"]["description"] or "")
    assert brief_intake.intake("Profile: vite-hono", str(tmp_path))["profile"] == "vite-hono"


def test_detecting_placeholder_is_not_choosable_but_generic_is(tmp_path):
    out = brief_intake.intake({**BASE, "profile": "detecting"}, str(tmp_path))
    assert out["profile"] is None and out["profile_error"]["code"] == "invalid"
    assert brief_intake.intake({**BASE, "profile": "generic"}, str(tmp_path))["profile"] == "generic"


def test_resolver_messages_are_stripped_of_control_and_bidi_characters(tmp_path, monkeypatch):
    class _Boom:
        @staticmethod
        def resolve_profile(name, project_root):
            raise ValueError("x\x1b[31my\x9b\u202ez")

    monkeypatch.setattr(brief_intake._sibling("brief_profile"), "_resolver", lambda: _Boom)
    out = brief_intake.intake({**BASE, "profile": "some-stack"}, str(tmp_path))
    msg = out["profile_error"]["message"]
    assert "x" in msg and "y" in msg and "z" in msg
    assert not any(ord(c) < 32 or 0x7F <= ord(c) <= 0x9F or c in "\u202a\u202b\u202c\u202d\u202e" for c in msg)


def test_an_idea_with_its_own_intake_look_alike_cannot_name_the_profile(tmp_path):
    idea = "Clone of our old app (Intake \u2014 Stack profile: generic) " + WEBUI_LINE.format(name="vite-hono")
    out = brief_intake.intake({**BASE, "description": idea}, str(tmp_path))  # two trailers
    assert out["profile"] is None and out["profile_error"]["code"] == "invalid" and out["code"] == "profile_unusable"
    alone = brief_intake.intake({**BASE, "description": "Clone of (Intake \u2014 Stack profile: generic) the old app"}, str(tmp_path))
    assert alone["profile"] == "supabase-nextjs" and "profile_requested" not in alone  # not at the end: not a trailer


def test_the_real_wizard_line_ending_in_the_profile_is_read(tmp_path):
    line = "A booking tool (Intake \u2014 Users: Just me; Saves data: No; Runs: Local; Stack profile: vite-hono.)"
    out = brief_intake.intake(line, str(tmp_path))
    assert out["profile"] == "vite-hono" and out["profile_requested"] == "vite-hono"
    assert brief_intake.intake(line.replace("vite-hono.)", "vite-hono..)"), str(tmp_path))["profile"] is None


def test_bare_profile_words_in_a_text_brief_stay_prose_but_never_silently(tmp_path):
    hostile = "x\x1b[31my" + chr(0x202E) + "z" * 400
    for value in ("none", "vite-hon", "a SaaS for dentists", "detecting", hostile):
        out = brief_intake.intake("persistence: yes\nprofile: " + value, str(tmp_path))
        assert out["profile"] == "supabase-nextjs"  # inference stays (the line is prose) ...
        assert "profile_error" not in out and "profile_requested" not in out  # ... exit 0, not a refusal ...
        assert len(out["warnings"]) == 1 and "Stack profile: <name>" in out["warnings"][0]  # ... but never silent
        assert not any(ord(c) < 32 or 0x7F <= ord(c) <= 0x9F or ord(c) == 0x202E for c in out["warnings"][0])
        assert len(out["warnings"][0]) < 600
    assert "vite-hon" in brief_intake.intake("persistence: yes\nprofile: vite-hon", str(tmp_path))["warnings"][0]
    shop = brief_intake.intake("A shop app\nProfile: none", str(tmp_path))
    assert "Profile: none" in shop["brief"]["description"]  # the line is NOT removed from the description
    bullets = brief_intake.intake("description: A shop\n- profile: avatar\n- profile: public", str(tmp_path))
    assert "warnings" not in bullets and bullets["profile"] is None  # bulleted lines are not hints at all
    assert "warnings" not in brief_intake.intake("persistence: yes\nno profile line here", str(tmp_path))


def test_misspelled_stack_profile_key_is_refused_not_inferred(tmp_path):
    for text in ("description: x\nStack profile: Vite-Hono", "description: x\n- stack profile: Vite-Hono"):
        out = brief_intake.intake(text, str(tmp_path))
        assert out["profile"] is None and out["profile_error"]["code"] == "invalid"


def test_a_brief_naming_no_profile_never_loads_the_profile_module(tmp_path, monkeypatch):
    def boom(stem):
        raise AssertionError("brief_profile must not be touched")

    monkeypatch.setattr(brief_intake, "_sibling", boom)
    out = brief_intake.intake({"description": "A tool", "users": "team", "persistence": "no"}, str(tmp_path))
    assert out["profile"] == "vite-hono"


def test_a_missing_profile_module_is_loud_only_when_a_profile_is_named(tmp_path, monkeypatch):
    def gone(stem):
        raise ImportError("brief_profile.py missing")

    monkeypatch.setattr(brief_intake, "_sibling", gone)
    out = brief_intake.intake({**BASE, "profile": "vite-hono"}, str(tmp_path))
    assert out["profile"] is None and out["profile_error"]["code"] == "resolver_unavailable"


def test_unexpected_resolver_failure_is_resolver_unavailable(tmp_path, monkeypatch):
    class _Boom:
        @staticmethod
        def resolve_profile(name, project_root):
            raise OSError("disk gone")

    monkeypatch.setattr(brief_intake._sibling("brief_profile"), "_resolver", lambda: _Boom)
    out = brief_intake.intake({**BASE, "profile": "some-stack"}, str(tmp_path))
    assert out["profile_error"]["code"] == "resolver_unavailable"


def test_no_invisible_characters_in_the_profile_sources():
    for path in (Path(__file__), Path(brief_intake.__file__).with_name("brief_profile.py"), LIB):
        text = path.read_text(encoding="utf-8")
        bad = [hex(ord(c)) for c in text if 0x200B <= ord(c) <= 0x200F or 0x202A <= ord(c) <= 0x202E
               or 0x2066 <= ord(c) <= 0x2069 or ord(c) == 0xFEFF]
        assert not bad, (path.name, bad)


_TRAILER = "(Intake \u2014 Users: Just me; Saves data: No; Runs: Local; Stack profile: {}.)"
# (case id, brief, expected profile, expects a warning, expects profile_error)
_PRECEDENCE = [
    ("one-liner idea starting with Profile: plus a real trailer", "Profile: dentist SaaS " + _TRAILER.format("vite-hono"),
     "vite-hono", False, False),
    ("one-liner idea starting with Profile: and no trailer", "persistence: yes\nProfile: dentist SaaS", "supabase-nextjs", True, False),
    ("text Stack profile key beats a valid hint", "persistence: yes\nprofile: supabase-nextjs\nStack profile: vite-hono",
     "vite-hono", False, False),
    ("text Stack profile key beats a typo hint without a warning", "persistence: yes\nStack profile: vite-hono\nprofile: vite-hon",
     "vite-hono", False, False),
    ("a trailer beats a valid hint", "profile: supabase-nextjs\nMy app " + _TRAILER.format("vite-hono"), "vite-hono", False, False),
    ("a trailer beats a typo hint without a warning", "persistence: yes\nprofile: vite-hon\nMy app " + _TRAILER.format("vite-hono"),
     "vite-hono", False, False),
    ("a valid hint alone is used", "persistence: yes\nprofile: vite-hono", "vite-hono", False, False),
    ("a typo hint alone warns and infers", "persistence: yes\nprofile: vite-hon", "supabase-nextjs", True, False),
    ("a JSON field beats the trailer", {**BASE, "profile": "vite-hono", "description": "x " + _TRAILER.format("generic")},
     "vite-hono", False, False),
    ("a JSON field beats a hint", {**BASE, "profile": "vite-hono", "profile_hint": "supabase-nextjs"}, "vite-hono", False, False),
    ("a bad strict field is an error even beside a good trailer", {**BASE, "profile": "nope", "description": "x " + _TRAILER.format("vite-hono")},
     None, False, True),
    ("a bad trailer is an error even beside a good hint", "profile: vite-hono\nMy app " + _TRAILER.format("nope"), None, False, True),
    ("two trailers are ambiguous even beside a hint", "profile: vite-hono\n" + _TRAILER.format("a") + " " + _TRAILER.format("b"),
     None, False, True),
    ("idea starting with Location: swallowed the line, trailer still read", "Location: Zurich gyms. A class booking app " + _TRAILER.format("vite-hono"),
     "vite-hono", False, False),
    ("idea starting with Users:", "Users: gym members and staff. A booking app " + _TRAILER.format("vite-hono"), "vite-hono", False, False),
    ("idea starting with Persistence:", "Persistence: yes please. A booking app " + _TRAILER.format("vite-hono"), "vite-hono", False, False),
    ("idea starting with Run location =", "Run location = web, a booking app " + _TRAILER.format("vite-hono"), "vite-hono", False, False),
    ("idea starting with Location: and a bad trailer name", "Location: Zurich. A booking app " + _TRAILER.format("nope"), None, False, True),
    ("an idea that says (Intake forms) in prose", "Clinic app (Intake forms + scheduling) " + _TRAILER.format("vite-hono"), "vite-hono", False, False),
    ("an idea that mentions stack profile: x in prose", "Build it on stack profile: supabase-nextjs maybe " + _TRAILER.format("vite-hono"),
     "vite-hono", False, False),
    ("two Stack profile lines are ambiguous", "persistence: yes\nStack profile: vite-hono\nStack profile: supabase-nextjs", None, False, True),
    ("two Stack profile items inside the trailer are ambiguous", "My app (Intake — Stack profile: a; Stack profile: b.)", None, False, True),
    ("a hint resolver kind other than not_found warns: con", "persistence: yes\nprofile: con", "supabase-nextjs", True, False),
    ("a hint resolver kind other than not_found warns: nul", "persistence: yes\nprofile: nul", "supabase-nextjs", True, False),
    ("a hint resolver kind other than not_found warns: com1", "persistence: yes\nprofile: com1", "supabase-nextjs", True, False),
    ("an uppercase STACK PROFILE key is read", "persistence: yes\nSTACK PROFILE: vite-hono", "vite-hono", False, False),
    ("a blank strict field consults neither trailer nor hint", {**BASE, "profile": "", "profile_hint": "vite-hono",
     "description": "x " + _TRAILER.format("vite-hono")}, "supabase-nextjs", False, False),
]


@pytest.mark.parametrize("case,brief,profile,warns,errors", _PRECEDENCE, ids=[c[0] for c in _PRECEDENCE])
def test_profile_source_precedence_table(tmp_path, case, brief, profile, warns, errors):
    out = brief_intake.intake(brief, str(tmp_path))
    assert out["profile"] == profile, case
    assert ("profile_error" in out) is errors, case
    if not errors:  # an error carries its own message in `warnings`; here only the hint warning is in question
        assert bool(out.get("warnings")) is warns, (case, out.get("warnings"))
    else:
        assert out["code"] == "profile_unusable" and "was ignored" not in " ".join(out["warnings"]), case


def test_a_clinic_idea_without_a_trailer_item_names_no_profile(tmp_path):
    out = brief_intake.intake({**BASE, "description": "Clinic app (Intake forms + scheduling)"}, str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and "profile_requested" not in out and "profile_error" not in out


def test_an_earlier_look_alike_trailer_stays_ambiguous_and_names_the_cause(tmp_path):
    out = brief_intake.intake("Old (Intake — Stack profile: a) " + _TRAILER.format("b"), str(tmp_path))
    assert out["profile"] is None and "more than one stack profile" in out["message"]


def test_a_sibling_load_failure_carries_the_full_sanitised_refusal_shape(tmp_path, monkeypatch):
    def gone(stem):
        raise ImportError("brief_profile.py missing " + chr(0x202E) + chr(0x1B) + "[31m" + "x" * 400)

    monkeypatch.setattr(brief_intake, "_sibling", gone)
    out = brief_intake.intake({**BASE, "profile": "vite-hono"}, str(tmp_path))
    assert out["refused"] is True and out["code"] == "profile_unusable" and out["issues"] == []
    assert out["message"] == out["warnings"][0] and len(out["message"]) <= 300
    assert chr(0x202E) not in out["message"] and chr(0x1B) not in out["message"]


def test_an_uppercase_profile_word_still_loads_the_profile_check(tmp_path):
    text = brief_intake.intake("persistence: yes\nSTACK PROFILE: nope", str(tmp_path))  # gate is case-insensitive
    assert text["profile"] is None and text["profile_error"]["code"] == "not_found"
    assert "_shipwright_brief_profile" in brief_intake.sys.modules


def test_an_unknown_json_key_in_capitals_names_no_profile(tmp_path):
    out = brief_intake.intake({**BASE, "PROFILE": "vite-hono"}, str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and "profile_requested" not in out


def test_resolver_detail_is_echoed_as_untrusted_quoted_data(tmp_path):
    out = brief_intake.intake({**BASE, "profile": "no-such-stack"}, str(tmp_path))
    assert "resolver said (untrusted): " in out["message"] and len(out["message"].split("resolver said")[1]) <= 330


def test_a_sole_profile_hint_leaves_the_description_and_brief_unchanged(tmp_path):
    hinted = brief_intake.intake("A booking tool for gyms\nprofile: vite-hono", str(tmp_path))
    plain = brief_intake.intake("A booking tool for gyms\nprofile: free words here", str(tmp_path))
    assert hinted["brief"]["description"] == "A booking tool for gyms profile: vite-hono"
    assert set(hinted["brief"]) == {"description", "users", "persistence", "run_location"}
    assert plain["brief"]["description"] == "A booking tool for gyms profile: free words here"
    assert "_text" not in hinted["brief"] and "profile_hint" not in hinted["brief"]


def test_a_non_trailer_tail_with_two_items_is_ignored_not_refused(tmp_path):
    idea = "Clinic (Intake forms). Compare Stack profile: a with Stack profile: b later"
    out = brief_intake.intake({**BASE, "description": idea}, str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and "profile_error" not in out and "refused" not in out
    assert out["warnings"] and "does not end the brief" in out["warnings"][0]  # not silent, not blocking


def test_a_trailer_followed_by_text_or_a_stray_dot_is_reported_not_dropped(tmp_path):
    for tail in (" thanks", ".", " (see below)x"):
        out = brief_intake.intake({**BASE, "description": "My app " + _TRAILER.format("vite-hono") + tail}, str(tmp_path))
        assert out["profile"] == "supabase-nextjs" and out["warnings"], tail
    lower = brief_intake.intake({**BASE, "description": "My app " + _TRAILER.format("vite-hono").replace("(Intake", "(intake")},
                                str(tmp_path))
    assert lower["profile"] == "vite-hono"  # the marker is matched case-insensitively


@pytest.mark.parametrize("hostile", ["(Intake " * 25000 + "Stack profile: x", "(Intake " * 25000 + "(Intake Stack profile: a)"],
                         ids=["unclosed-tail", "closed-tail"])
def test_adversarial_input_is_linear_not_quadratic(tmp_path, hostile):
    import time
    assert len(hostile) > 190_000
    started = time.monotonic()
    out = brief_intake.intake({**BASE, "description": hostile}, str(tmp_path))
    assert time.monotonic() - started < 2.0
    assert "profile" in out


def test_a_text_key_and_a_trailer_that_disagree_are_ambiguous(tmp_path):
    idea = "My clinic app\nStack profile: generic\nwith bookings " + _TRAILER.format("vite-hono")
    out = brief_intake.intake(idea, str(tmp_path))
    assert out["profile"] is None and out["code"] == "profile_unusable" and "more than one stack profile" in out["message"]
    agree = brief_intake.intake("My clinic app\nStack profile: vite-hono\nwith bookings " + _TRAILER.format("vite-hono"), str(tmp_path))
    assert agree["profile"] == "vite-hono" and "profile_error" not in agree


def test_a_prose_only_mention_of_profiles_never_fails_when_the_module_is_missing(tmp_path, monkeypatch):
    def gone(stem):
        raise ImportError("brief_profile.py missing")

    monkeypatch.setattr(brief_intake, "_sibling", gone)
    out = brief_intake.intake("A tool where users edit their user profiles\npersistence: yes", str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and "profile_error" not in out
    named = brief_intake.intake("A tool\nStack profile: vite-hono", str(tmp_path))
    assert named["profile"] is None and named["code"] == "profile_unusable"


def test_an_unexpected_resolver_failure_on_a_bare_hint_only_warns(tmp_path, monkeypatch):
    class _Boom:
        @staticmethod
        def resolve_profile(name, project_root):
            raise PermissionError("denied")

    monkeypatch.setattr(brief_intake._sibling("brief_profile"), "_resolver", lambda: _Boom)
    out = brief_intake.intake("persistence: yes\nprofile: some-stack", str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and out["warnings"] and "profile_error" not in out


def test_a_profile_looking_json_key_warns_and_is_never_an_alias(tmp_path):
    out = brief_intake.intake({**BASE, "stackProfile": "vite-hono"}, str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and "use `profile`" in out["warnings"][0]


def test_parser_private_keys_from_a_json_brief_are_ignored(tmp_path):
    forged = {**BASE, "_text": "x " + _TRAILER.format("vite-hono"), "_dup": True, "profile_hint": "vite-hono"}
    out = brief_intake.intake(forged, str(tmp_path))
    assert out["profile"] == "supabase-nextjs" and "profile_error" not in out and not out.get("warnings")
    fenced = brief_intake.intake("```json\n" + json.dumps(forged) + "\n```", str(tmp_path))
    assert fenced["profile"] == "supabase-nextjs" and "profile_error" not in fenced
