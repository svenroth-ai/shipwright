"""Which shell commands are an outward release action (P4b; second pass B2).

Pure text in, facts out: no git, no files, no environment, so every form is testable without a repository. The hook
(``release_guard.py``) turns the facts into a decision. The outward actions are ``git push`` (of a tag or of a trunk),
``gh pr merge`` and ``gh release create``.

The command is lexed the way ``release_runstate`` callers type it on Windows: ``shlex`` in **non-POSIX** mode, so a
backslash path (``git -C C:\\repo push``) is not eaten as an escape, and quoted text stays one token (``-m "git push"`` and
``echo 'gh pr merge'`` are data, never a command). Segments split on ``&& || ; | &`` and newlines; here-document bodies are
blanked first. Known misses (the hook is a net against a forgetful model, not an adversarial boundary): a command wrapped
in ``bash -c '...'`` / ``eval``, a variable or command substitution as the program or refspec, ``push.followTags`` in git
config, ``gh release edit``, and an unbalanced quote (the whole line is then not read).
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

_HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_]\w*)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.DOTALL)
_HERESTRING = re.compile(r"@([\"'])[ \t]*\r?\n.*?\r?\n[ \t]*\1@", re.DOTALL)  # PowerShell @"..."@ / @'...'@
_PROTECT = {c: chr(0xE000 + i) for i, c in enumerate(";|&()<>\n")}  # separators inside quotes are data
_RESTORE = {v: k for k, v in _PROTECT.items()}
_ASSIGNMENT = re.compile(r"[A-Za-z_]\w*=")
_SEPARATORS = {"&&", "||", ";", ";;", "|", "|&", "&", "(", ")"}
_SKIPPED = {"env", "command", "exec", "time", "nohup", "sudo", "nice", "if", "then", "else", "elif", "do", "while", "until",
            "!", "{", "}"}
_PUSH_VALUE_OPTIONS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
_GIT_VALUE_OPTIONS = {"-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env"}
_GH_VALUE_OPTIONS = {"-R", "--repo", "--hostname", "-b", "--body", "-F", "--body-file", "-t", "--subject", "--match-head-commit",
                     "--author-email"}
_CD = {"cd", "pushd", "set-location", "sl"}
_POP = {"popd", "pop-location"}


@dataclass
class Action:
    """One outward action found in a command line."""

    kind: str  # "push" | "merge" | "release"
    c_paths: list[str] = field(default_factory=list)  # every ``git -C <path>``, in order
    all_refs: bool = False  # --all / --mirror: every branch goes, the trunk included
    tags: bool = False  # --tags / --follow-tags / --mirror / refs/tags/... / `tag <name>`
    refs: list[str] = field(default_factory=list)  # destination names (a plain name, or ``HEAD``); empty = the current branch
    target: str = ""  # gh pr merge: the PR number, URL or branch it names; empty = the current branch's PR
    foreign: bool = False  # gh -R / --repo: another repository, not this checkout
    cwd_unknown: bool = False  # a popd / Pop-Location / ``cd $var`` earlier in the line: the directory cannot be known


def _unquote(token: str) -> str:
    return token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'" else token


def _protect_quoted(text: str) -> str:
    """Hide the separator characters that sit inside a quoted span, also one that starts mid-token (``--message="a; b"``)."""
    out, quote, i = [], "", 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(text):
                out.append(ch + text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
            out.append(_PROTECT.get(ch, ch) if quote else ch)
        else:
            quote = ch if ch in "\"'" else ""
            out.append(ch)
        i += 1
    return "".join(out)


def segments(command: str) -> list[list[str]]:
    """The command split into simple commands, each a list of unquoted tokens. A lexing error yields no segments (fail open)."""
    text = _HERESTRING.sub(" ", _HEREDOC.sub(" ", command.replace("\r", "").replace("\\\n", " ")))
    text = _protect_quoted(text).replace("\n", " ; ")
    try:
        lexer = shlex.shlex(text, posix=False, punctuation_chars=True)
        lexer.whitespace_split, lexer.commenters = True, ""
        tokens = list(lexer)
    except ValueError:
        return []
    out: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEPARATORS:
            out.append([])
        else:
            out[-1].append(token)
    result = []
    for seg in out:
        for i, token in enumerate(seg):  # a redirection ends the arguments: ``> out.txt`` and ``2>&1`` are not refspecs
            if re.fullmatch(r"[<>&|]*[<>][<>&|]*", token):
                seg = seg[: i - 1] if i and seg[i - 1].isdigit() else seg[:i]
                break
        if seg:
            result.append([_unquote(t).translate(str.maketrans(_RESTORE)) for t in seg])
    return result


def _program(seg: list[str]) -> tuple[str, list[str]]:
    i = 0
    while i < len(seg) and (_ASSIGNMENT.match(seg[i]) or seg[i] in _SKIPPED):
        i += 1
    if i >= len(seg):
        return "", []
    name = re.split(r"[\\/]", seg[i])[-1].lower()
    return re.sub(r"\.(exe|cmd|bat)$", "", name), seg[i + 1:]


def _push(args: list[str], c_paths: list[str]) -> Action:
    act = Action("push", c_paths=c_paths)
    positional: list[str] = []
    repo_given, i = False, 0
    while i < len(args):
        arg = args[i]
        if arg in ("--tags", "--follow-tags"):
            act.tags = True
        elif arg in ("--all", "--mirror"):
            act.all_refs, act.tags = True, act.tags or arg == "--mirror"
        elif arg in _PUSH_VALUE_OPTIONS:
            repo_given = repo_given or arg == "--repo"
            i += 1
        elif arg.startswith("--repo="):
            repo_given = True
        elif not arg.startswith("-") or arg == "-":
            positional.append(arg)
        i += 1
    if not repo_given and len(positional) >= 2 and positional[1] == "tag":  # git push <remote> tag <name>
        act.tags, positional = True, positional[:1]
    for spec in positional if repo_given else positional[1:]:  # positional[0] is the remote unless --repo named it
        dst = spec.lstrip("+")
        dst = dst.split(":", 1)[1] if ":" in dst else dst
        if dst.startswith("refs/tags/"):
            act.tags = True
        elif dst:
            act.refs.append(dst.removeprefix("refs/heads/"))
    return act


def _git(args: list[str]) -> Action | None:
    c_paths: list[str] = []
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] == "-C" and i + 1 < len(args):
            c_paths.append(args[i + 1])
            i += 1
        elif args[i] in _GIT_VALUE_OPTIONS:
            i += 1
        i += 1
    return _push(args[i + 1:], c_paths) if i < len(args) and args[i] == "push" else None


def _gh(args: list[str]) -> Action | None:
    positional, foreign, i = [], False, 0
    while i < len(args):
        if args[i] in _GH_VALUE_OPTIONS:
            foreign = foreign or args[i] in ("-R", "--repo")
            i += 1
        elif args[i].startswith("--repo="):
            foreign = True
        elif not args[i].startswith("-"):
            positional.append(args[i])
        i += 1
    if positional[:2] == ["pr", "merge"]:
        return Action("merge", target=positional[2] if len(positional) > 2 else "", foreign=foreign)
    return Action("release", foreign=foreign) if positional[:2] == ["release", "create"] else None


def find_actions(command: str) -> list[Action]:
    """Every outward release action the command line contains (empty for an ordinary command). A ``cd``/``pushd``/``Set-Location``
    in an earlier segment aims the later ones: it is carried as a leading ``c_paths`` entry. ``popd``/``Pop-Location`` and a
    ``$``-built target make the directory unknown (``cwd_unknown``)."""
    found, moved, unknown = [], [], False
    for seg in segments(command):
        program, args = _program(seg)
        if program in _POP:
            unknown = True
            continue
        if program in _CD:
            target = next((a for a in args if not a.startswith("-")), "")
            if "$" in target or "`" in target:
                unknown = True
            elif target:
                moved.append(target)
            continue
        action = _git(args) if program == "git" else _gh(args) if program == "gh" else None
        if action:
            action.c_paths, action.cwd_unknown = [*moved, *action.c_paths], unknown
            found.append(action)
    return found
