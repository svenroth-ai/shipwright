"""The command substitutions inside a shell command line (``git_commit_command``).

``echo "$(git commit -m x)"`` and ``echo `git commit` `` run a commit that no
word-level split sees, because the substitution sits inside a quoted word or behind a
backtick. :func:`substitutions` returns the TOP-LEVEL bodies of ``$(...)``, backticks
and ``<(...)`` / ``>(...)``; the caller parses each as a command line again (which finds
the nested ones). Single quotes and a backslash hide a substitution, as in the shell;
``$((...))`` is arithmetic, not a command. An unterminated substitution takes the rest
of the text (over-fires, never fails open).

Pure, stdlib-only.
"""

from __future__ import annotations


def _backtick(text: str, i: int) -> tuple[str, int]:
    """``(body, index after)`` of the backtick substitution opening at ``text[i]``."""
    j, n = i + 1, len(text)
    while j < n and text[j] != "`":
        j += 2 if text[j] == "\\" else 1
    return text[i + 1:j].replace("\\`", "`"), j + 1


def _paren(text: str, i: int, out: list[str]) -> int:
    """Scan from *i* (just past an opening paren) to its closing paren; its body goes to *out*.

    Returns the index after the closing paren (``len(text)`` when unclosed).
    """
    end = _scan(text, i, True, [])
    out.append(text[i:end - 1] if text[end - 1:end] == ")" and end > i else text[i:end])
    return end


def _scan(text: str, i: int, in_paren: bool, out: list[str]) -> int:
    n, dq, depth = len(text), False, 0
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
        elif ch == "'" and not dq:
            close = text.find("'", i + 1)
            i = n if close < 0 else close + 1
        elif ch == '"':
            dq = not dq
            i += 1
        elif ch == "#" and in_paren and not dq and (i == 0 or text[i - 1] in " \t\n;&|()"):
            newline = text.find("\n", i)  # a comment: its ``)`` closes nothing
            i = n if newline < 0 else newline
        elif ch == "`":
            body, i = _backtick(text, i)
            out.append(body)
        elif text.startswith("$((", i):
            k = _scan(text, i + 3, True, [])  # the close of the SECOND paren, as bash reads it
            if text[k:k + 1] != ")":  # `$((cmd) ...)` is a substitution around a subshell
                i = _paren(text, i + 2, out)
                continue
            _scan(text[i + 3:k - 1], 0, False, out)  # `$(( $(cmd) + 1 ))` still runs cmd
            i = k + 1
        elif text.startswith("$(", i) or (not dq and text[i:i + 2] in ("<(", ">(")):
            i = _paren(text, i + 2, out)
        else:
            if in_paren and not dq and ch in "()":
                if ch == ")" and depth == 0:
                    return i + 1
                depth += 1 if ch == "(" else -1
            i += 1
    return n


def substitutions(text: str) -> list[str]:
    """The top-level command-substitution bodies in *text*, in order."""
    out: list[str] = []
    _scan(text, 0, False, out)
    return out
