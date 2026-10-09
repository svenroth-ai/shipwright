"""The commit hook reads the command shapes it used to misread (U13 follow-ups).

Heredoc/continuation order and odd delimiters, every commit of a nested shell call,
commits inside command substitutions, unparseable text. Over-firing is the safe direction.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import git_commit_command as gcc  # noqa: E402
import shell_heredoc  # noqa: E402
import shell_substitution  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.10")


# --- heredoc: continuations first, odd delimiters and unclosed bodies stay visible --------

@pytest.mark.parametrize("command", [
    "cat <<E\\\nOF\ngit commit -m x\nEOF",  # delimiter split by a continuation is EOF: data
    "cat <<EOF \\\n> f\ngit commit -m x\nEOF",
])
def test_a_continued_operator_line_still_hides_its_body(command):
    assert not gcc.is_git_commit(command)


@pytest.mark.parametrize("command", [
    "cat <<E\\OF\nbody\nE\ngit commit -m x\nEOF",  # backslash in the delimiter: not read
    'cat <<EO"F"\nbody\nEO\ngit commit -m x\nEOF',
    "cat <<E$X\nbody\nE\ngit commit -m x\nEOF",
    "cat <<EOF\ngit commit -m x",  # never closed
    "cat <<EOF\nnote\nEOF2\ngit commit -m x",  # the delimiter line is never exact
])
def test_an_odd_or_unclosed_delimiter_keeps_the_body_visible(command):
    assert gcc.is_git_commit(command)


def test_a_commit_after_a_continued_heredoc_is_still_found():
    assert gcc.is_git_commit("cat <<E\\\nOF > f\nbody\nEOF\ngit commit -m x")
    assert "body" not in shell_heredoc.strip_heredoc_bodies("cat <<E\\\nOF > f\nbody\nEOF")


def test_continuations_inside_a_quoted_body_are_literal():
    """bash does not join backslash-newline in a quoted body: the next EOF still closes it."""
    command = "cat > a.sh <<'EOF'\necho one \\\nEOF\ngit commit -m x\ncat > b.txt <<'EOF'\ntext\nEOF"
    assert gcc.is_git_commit(command)
    assert "echo one" not in shell_heredoc.strip_heredoc_bodies(command)


def test_a_backslash_ending_a_quoted_body_line_does_not_hide_a_later_commit():
    command = "cat > a <<'EOF'\nC:\\dir\\\nEOF\ngit commit -m x\ncat > b <<'EOF'\ny\nEOF"
    assert gcc.is_git_commit(command)


def test_an_escaped_backslash_before_a_newline_does_not_hide_the_next_commit():
    assert gcc.is_git_commit("cp a.txt C:\\\\tmp\\\\\ngit commit -m x")


def test_absurd_nesting_over_fires_instead_of_crashing():
    command = "echo " + "$(" * 2000 + "git commit -m x" + ")" * 2000
    assert gcc.is_git_commit(command)


def test_a_trailing_continuation_at_the_end_is_kept():
    assert gcc.is_git_commit("git commit -m x \\")
    assert gcc.is_git_commit("git \\\ncommit -m x")


@pytest.mark.parametrize("command", [
    "# Let's commit the fix\ngit -C .worktrees/x commit -m y",  # a stray quote: shlex gives up
    "cat <<\\EOF > notes\nwe don't\nEOF\ngit --no-pager commit -m x",
])
def test_unparseable_text_still_finds_a_git_commit(command):
    assert gcc.is_git_commit(command)


def test_unparseable_text_keeps_the_commit_location():
    found = list(gcc.iter_git_commits("# Let's go\ngit -C ../b commit -m y\ngit --git-dir=/x/.git commit"))
    assert found == [("-C", "../b"), ("--git-dir=/x/.git",)]
    assert list(gcc.iter_git_commits("echo don't; git commit -m x")) == [()]


def test_unparseable_text_without_a_commit_does_not_fire():
    assert not gcc.is_git_commit("echo don't; git status")


# --- nested shell calls: every inner commit counts --------------------------------------

@pytest.mark.parametrize("command, count", [
    ("bash -c 'git -C a commit -m x; git -C b commit -m y'", 2),
    ("eval git -C a commit -m x '&&' git -C b commit -m y", 2),
    ('pwsh -Command "git -C a commit -m x; git -C b commit -m y"', 2),
    ('sh -c "git commit -m a && git commit -m b" && git commit -m c', 3),
    ("bash -c 'echo hi; git commit -m x'", 1),
])
def test_every_inner_commit_of_a_nested_shell_is_listed(command, count):
    assert len(list(gcc.iter_git_commits(command))) == count


@pytest.mark.parametrize("command", [
    "eval git -C a commit -m x '&&' git -C b commit -m y",
    'pwsh -Command "git -C a commit -m x; git -C b commit -m y"',
    'cmd /c "git -C a commit -m x & git -C b commit -m y"',
    'powershell.exe -NoProfile -c "git -C a commit -m x; git -C b commit -m y"',
])
def test_each_wrapper_lists_the_exact_inner_locations(command):
    assert list(gcc.iter_git_commits(command)) == [("-C", "a"), ("-C", "b")]


def test_env_split_string_lists_every_inner_commit():
    found = list(gcc.iter_git_commits(
        "env -S \"bash -c 'git -C a commit -m x; git -C b commit -m y'\""))
    assert found == [("-C", "a"), ("-C", "b")]


def test_inner_commits_keep_their_own_global_options():
    found = list(gcc.iter_git_commits("bash -c 'git -C a commit -m x; git -C b commit -m y'"))
    assert found == [("-C", "a"), ("-C", "b")]


# --- command substitutions ---------------------------------------------------------------

@pytest.mark.parametrize("command", [
    'echo "$(git commit -m x)"',
    "echo `git commit -m x`",
    "x=$(git commit -m x)",
    "diff <(git commit -m x) f",
    'echo "a $(echo $(git commit -m x)) b"',
    'echo "$(git status; git commit -m x)"',
    'bash -c \'echo "$(git commit -m x)"\'',
    'echo "$(git commit -m x"',  # unterminated: the rest is taken
    'echo "$(( $(git -C a commit -m x | wc -l) + 1 ))"',  # inside arithmetic
    'echo "$((git commit -m x) )"',  # not arithmetic: a subshell in a substitution
    'echo "$((git commit -m x) && (true))"',  # the second paren closes early: a command
    "echo \"$((git commit -m '))') )\"",  # quoted parens do not end the span
])
def test_a_commit_inside_a_substitution_fires(command):
    assert gcc.is_git_commit(command)


@pytest.mark.parametrize("command", [
    "echo '$(git commit -m x)'",
    'echo "\\$(git commit -m x)"',
    "echo \\`git commit\\`",
    'echo "$(git status)"',
    "echo $((1 + 2))",
    "echo $(( (1+2) * 3 ))",
    'git log --grep "$(echo git commit)"',
    "git commit-tree HEAD^{tree}",
])
def test_text_that_only_mentions_a_commit_does_not_fire(command):
    assert not gcc.is_git_commit(command)


def test_the_canonical_heredoc_message_substitution_is_not_a_second_commit():
    command = "git commit -m \"$(cat <<'EOF'\ngit commit -m inside\nEOF\n)\""
    assert len(list(gcc.iter_git_commits(command))) == 1


def test_a_substitution_commit_carries_its_own_location():
    found = list(gcc.iter_git_commits('echo "$(git -C other commit -m x)"'))
    assert ("-C", "other") in found


def test_substitution_bodies_are_top_level_only():
    assert shell_substitution.substitutions('a "$(b $(c))" `d`') == ["b $(c)", "d"]
    assert shell_substitution.substitutions("echo '$(x)' \\$(y)") == []


def test_substitutions_share_the_depth_bound():
    nested = "git commit"
    for _ in range(gcc._MAX_SHELL_DEPTH + 2):
        nested = f"echo $({nested})"
    assert gcc.is_git_commit(nested)  # past the cap the substring test over-fires


@pytest.mark.parametrize("command", [
    "echo hi # note \\\ngit commit -m x",  # a comment ends at its newline, not at the backslash
    "(( y = x <<EOF ))\ngit commit -m x\nEOF",  # arithmetic: << is a shift, not a heredoc
    "diff >(git commit -m x) f",
    "bash -c -- 'git commit -m x'",
    "cat <<EOF\r\nbody\r\nEOF2\r\ngit commit -m x",  # CRLF, delimiter never exact
])
def test_review_round_shapes_fire(command):
    assert gcc.is_git_commit(command)


def test_a_continuation_inside_an_unquoted_body_joins_the_delimiter():
    """bash joins `EO` + backslash-newline + `F` into EOF in an unquoted body: the commit runs."""
    assert gcc.is_git_commit("cat <<EOF\nEO\\\nF\ngit commit -m x\nEOF")
    quoted = "cat <<'EOF'\nEO\\\nF\ngit commit -m x\nEOF"  # literal in a quoted body: all data
    assert not gcc.is_git_commit(quoted)


def test_a_paren_in_a_comment_does_not_close_a_substitution():
    command = 'echo "$(echo hi # )\ngit -C other commit -m x)"'
    assert ("-C", "other") in list(gcc.iter_git_commits(command))


def test_an_apostrophe_idiom_does_not_hide_a_later_substitution():
    assert gcc.is_git_commit("echo 'it'\\''s ok'; echo \"$(git commit -m x)\"")


def test_unparseable_text_keeps_a_quoted_path_with_spaces():
    found = list(gcc.iter_git_commits("# Let's go\ngit -C \"/project b\" commit -m y"))
    assert found == [("-C", "/project b")]


def test_the_depth_cap_fallback_reads_git_dash_c_commit_too():
    assert gcc.is_git_commit("eval " * 5 + "git -C x commit")
    assert gcc.is_git_commit("cmd /c " * 5 + "git.exe  commit")
    assert not gcc.is_git_commit("eval " * 5 + "git -C x status")


def test_every_commit_on_an_unparseable_line_keeps_its_own_location():
    found = list(gcc.iter_git_commits("echo don't; git -C a commit -m x; git -C b commit -m y"))
    assert found == [("-C", "a"), ("-C", "b")]


def test_the_fallback_option_pattern_does_not_backtrack_catastrophically():
    import time

    started = time.monotonic()
    gcc.is_git_commit("git" + " -c" * 40 + " x'")
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("command", [
    "bash <<'EOF'\ngit \\\ncommit -m x\nEOF",  # a quoted body fed to a shell is a script
    "cat <<'EOF' | sh\ngit \\\ncommit -m x\nEOF",
])
def test_a_continuation_in_a_shell_fed_quoted_body_joins(command):
    assert gcc.is_git_commit(command)
