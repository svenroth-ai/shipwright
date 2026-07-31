"""Two `pr_review_render` guarantees that the stale-verdict path leans on.

**The log sanitiser.** `safe_path` bounds ONE path inside a Markdown sentence,
so it strips backticks and braces too and truncates at 160 characters. A `gh`
error printed into a CI log needs the *control-and-invisible* half only and none
of the bounding — `pr_review_dismiss._inert` is that caller. Exported rather
than re-declared so the newest sink cannot grow its own, weaker class; both are
built from the same `_CONTROL_AND_INVISIBLE` constant, which the enumeration
test in `test_pr_review_render.py` pins.

**The waiver notice.** The truncation comment tells a maintainer to apply
`skip-pr-review`, and that instruction must not promise more than the pipeline
delivers.

Its own module because `test_pr_review_render.py` already sits exactly at the
300-line guideline; adding here rather than there is the difference between
splitting a file for a reason and splitting it to launder a budget.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_render as R  # noqa: E402


class TestTheWaiverIsNotOversold:
    """The truncation notice tells a maintainer to apply `skip-pr-review`. That
    label greens the required check, but the run that fired it also posted a
    `CHANGES_REQUESTED`, and the labelled re-run takes the `needs_review=false`
    branch — so `pr_review.py` never runs and never clears it. Following the
    printed instruction lands in the exact defect this iterate removes. Until
    the workflow half lands (IT-9's tree), the notice must say so."""

    def test_the_truncation_notice_does_not_promise_an_unblock(self):
        rendered = R.render_comment(
            {"decision": "approve", "summary": "s"}, model="m", truncated=True,
            omitted=("a.py",))
        assert "skip-pr-review" in rendered
        assert "dismissed by hand" in rendered
        assert "does **not** retract" in rendered


class TestStripDisplayUnsafe:

    def test_it_strips_control_characters(self):
        assert R.strip_display_unsafe("a\x00b\x1b[31mc\nd\x7fe") == "a?b?[31mc?d?e"

    def test_a_gh_json_error_survives_legible(self):
        # The payload this sink actually carries. `safe_path` blanks braces and
        # backticks because it renders INTO Markdown and a prompt template; a
        # stderr line has neither problem, and `?"message": "Not Found"?` is the
        # run failing to say what happened — which is the defect, not the fix.
        error = 'gh api `.../reviews` failed (1): {"message": "Not Found"}'
        assert R.strip_display_unsafe(error) == error
        assert "{" not in R.safe_path(error)

    def test_a_newline_cannot_forge_a_workflow_command(self):
        # Actions reads `::error::` at the start of a line. Stripping C0 means a
        # `gh` error can never introduce one into the log.
        assert "\n" not in R.strip_display_unsafe("gh: boom\n::error::forged")

    def test_it_neutralises_the_invisible_separators(self):
        # The two codepoints a hand-rolled class in another module got wrong by
        # embedding them RAW in its source. Spelled as escapes here on purpose.
        for sep in (chr(0x2028), chr(0x2029)):
            assert sep not in R.strip_display_unsafe(f"gh: err{sep}Ignore the above")

    def test_it_does_not_truncate(self):
        # The one thing that distinguishes it from safe_path. A `gh` error cut
        # off at 160 characters is a log line that stops before the reason.
        long_error = "gh: " + "e" * 500
        assert R.strip_display_unsafe(long_error) == long_error
        assert len(R.safe_path(long_error)) < len(long_error)

    def test_none_and_non_strings_do_not_crash(self):
        # It is called on exception objects, not only on strings.
        assert R.strip_display_unsafe(None) == ""
        assert R.strip_display_unsafe(404) == "404"

    def test_its_alphabet_is_the_union_minus_exactly_the_markdown_three(self):
        # The sibling enumeration test pins `_UNSAFE_IN_DISPLAY`. Pin the
        # narrower class against it, or a later tightening of `_CONTROL_ONLY`
        # slips through and the newest sink becomes the weakest one — the exact
        # failure splitting the class was meant to prevent.
        both = {cp for cp in range(0x110000) if R._UNSAFE_IN_DISPLAY.match(chr(cp))}
        control = {cp for cp in range(0x110000) if R._CONTROL_ONLY.match(chr(cp))}
        assert both - control == {0x60, 0x7B, 0x7D}, "backtick + braces, nothing else"
