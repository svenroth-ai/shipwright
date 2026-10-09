"""Decide whether a shell command force-pushes to main/master.

Used by validate_command.sh. Reads the command from stdin; exits BLOCK_EXIT
(3) to block, 0 to allow, and UNDECIDED_EXIT (4) on an internal error — the
caller then falls back to its coarse check, so a bug here can neither pass a
force push silently nor block unrelated commands for good.

Only the ``git push`` segment is inspected: the command is tokenised
quote-aware, split on shell separators and newlines (heredoc bodies are data,
not commands), the force flag must be a whole argument of the push (-f, a
short cluster containing f, --force, --force-with-lease, a +refspec), and
main/master must be the push target.

Known limits (a denylist over shell text, not a sandbox): a quoted string that
spans several lines is inspected line by line, so prose inside it that looks
like a force push can still block; an argument-less force push is judged by the
hook's own checkout (or ``git -C``), not by a preceding ``cd``; ``--tags`` with
no refspec on a protected checkout is treated like any argument-less push.
"""
import re
import shlex
import subprocess
import sys

BLOCK_EXIT = 3
UNDECIDED_EXIT = 4  # internal error: the caller falls back to its coarse check
PROTECTED = {"main", "master"}
# push options that consume the following token as their value
VALUE_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "bash.exe", "sh.exe"}
# tokens that may precede the real executable of a simple command
WRAPPERS = {
    "sudo", "env", "command", "time", "nohup", "exec", "nice", "xargs",
    "builtin", "stdbuf", "timeout", "then", "do", "else", "elif", "if",
    "while", "until", "!", "{", "}",
}
# wrapper options that consume the following token (sudo -u bob git ...)
WRAPPER_VALUE_OPTS = {"-u", "-g", "-h", "-p", "-C", "-n", "-s", "-k"}


def _tokens(line):
    lex = shlex.shlex(line, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""  # bash treats # as a comment only at word start
    return list(lex)


def _basename(tok):
    return tok.replace("\\", "/").rsplit("/", 1)[-1]


def _emit(seg):
    yield seg
    yield from _nested(seg)


def segments(cmd):
    """Yield token lists, one per simple command (recursing into -c strings)."""
    heredoc_end = None  # delimiter of the heredoc body being skipped
    cmd = re.sub(r"\\\r?\n", " ", cmd)  # backslash line continuations
    for line in cmd.splitlines():
        if heredoc_end is not None:
            if line.strip() == heredoc_end:
                heredoc_end = None
            continue
        if line.lstrip().startswith("#"):  # whole-line comment
            continue
        # command substitution starts a nested command: treat it as a separator
        line = line.replace("$(", " ; ").replace("`", " ; ")
        try:
            tokens = _tokens(line)
            for n, tok in enumerate(tokens):
                if tok.startswith("#"):  # inline comment: rest of the line
                    tokens = tokens[:n]
                    break
        except ValueError:  # unbalanced quotes: fall back to a plain split
            for part in re.split(r"&&|\|\||[;|&]", line):
                yield from _emit(part.split())
            continue
        seg, skip, want_delim = [], False, False
        for tok in tokens:
            if want_delim:
                heredoc_end = tok.lstrip("-") if tok.startswith("-") else tok
                want_delim = skip = False
            elif skip:  # redirect target
                skip = False
            elif tok in ("<<", "<<-"):
                want_delim = True
            elif set("<>") & set(tok) and set(tok) <= set("<>&|"):
                skip = True  # redirect operator (>, 2>&1, &>, >|): drop its target
                if seg and seg[-1].isdigit():  # and the fd number before it
                    seg.pop()
            elif tok and set(tok) <= set("&|;()"):
                yield from _emit(seg)
                seg = []
            else:
                seg.append(tok)
        yield from _emit(seg)


def _nested(seg):
    """Commands passed as a string to a shell (``bash -c "..."``) or eval."""
    exe = _exe_index(seg)
    if exe is None:
        return
    head = _basename(seg[exe])
    rest = seg[exe + 1:]
    if head == "eval":
        yield from segments(" ".join(rest))
    elif head in SHELLS:
        for prev, tok in zip(rest, rest[1:]):
            if prev.startswith("-") and not prev.startswith("--") and "c" in prev[1:]:
                yield from segments(tok)


def _exe_index(seg):
    """Index of the command actually executed, skipping VAR=x and wrappers."""
    i, wrapped, operand = 0, False, False
    while i < len(seg):
        tok = seg[i]
        if re.match(r"^\w+=", tok):
            i += 1
        elif tok in WRAPPERS:
            wrapped = True
            operand = tok == "timeout"  # timeout takes a duration operand
            i += 1
        elif operand and not tok.startswith("-"):
            operand = False
            i += 1
        elif wrapped and tok.startswith("-"):
            i += 2 if tok in WRAPPER_VALUE_OPTS else 1
        else:
            return i
    return None


def push_args(seg):
    """``(args, git_cwd)`` after ``git ... push``, or None if not a push."""
    exe = _exe_index(seg)
    if exe is None or _basename(seg[exe]) not in ("git", "git.exe"):
        return None
    i, cwd = exe + 1, None
    while i < len(seg) and seg[i].startswith("-"):  # git-level options
        if seg[i] == "-C" and i + 1 < len(seg):
            cwd = seg[i + 1]
        i += 2 if seg[i] in GIT_VALUE_OPTS else 1
    if i < len(seg) and seg[i] == "push":
        return seg[i + 1:], cwd
    return None


def target_of(refspec):
    dst = refspec.lstrip("+")
    if ":" in dst:
        dst = dst.split(":", 1)[1]
    return re.sub(r"^refs/heads/", "", dst)


def checked_out_destinations(cwd):
    """Branch names an argument-less push would update: HEAD and its upstream."""
    names = []
    for ref in ("HEAD", "@{upstream}"):
        try:
            out = subprocess.run(
                ["git"] + (["-C", cwd] if cwd else []) + ["rev-parse", "--abbrev-ref", ref],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            continue
        name = out.stdout.strip()
        if out.returncode == 0 and name:
            names.append(name.split("/", 1)[1] if ref != "HEAD" and "/" in name else name)
    return names


def blocked(args, cwd=None):
    forced = sweeping = False
    positional, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif arg in VALUE_OPTS:
            skip = True
        elif arg in ("--all", "--mirror"):
            sweeping = True
        elif arg == "--force" or arg.startswith("--force-"):
            forced = True
        elif arg.startswith("--"):
            continue
        elif arg.startswith("-") and len(arg) > 1:
            for ch in arg[1:]:
                if ch == "o":  # the rest of the token (or the next one) is a value
                    skip = arg.endswith("o")
                    break
                forced = forced or ch == "f"
        else:
            positional.append(arg)
    refspecs = positional[1:]  # the first positional is the remote
    if len(positional) == 1 and target_of(positional[0]) in PROTECTED:
        refspecs = positional  # `push -f main`: git itself rejects the ambiguity
    if sweeping and forced:
        return True
    for refspec in refspecs:
        if target_of(refspec) in PROTECTED and (forced or refspec.startswith("+")):
            return True
    # No explicit branch (or HEAD): the push goes to the current/upstream branch.
    if forced and (not refspecs or all(target_of(r) in ("HEAD", "@") for r in refspecs)):
        return any(name in PROTECTED for name in checked_out_destinations(cwd))
    return False


def main():
    try:
        cmd = sys.stdin.buffer.read().decode("utf-8", "replace")
        for seg in segments(cmd):
            parsed = push_args(seg)
            if parsed is not None and blocked(*parsed):
                return BLOCK_EXIT
    except Exception:
        return UNDECIDED_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(main())
