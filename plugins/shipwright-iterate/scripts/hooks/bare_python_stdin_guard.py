#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code hook: refuse a Bash command that runs ``python -`` with nothing behind it.

``python -`` reads its program from stdin. With no heredoc, pipe or ``<`` feeding it, the
interpreter sits on a stdin nobody answers. Two runner subagents emitted
``python - 2>/dev/null; uv run python -c ...`` and ``python - <<'EOF' 2>/dev/null || uv run
python - <<'EOF2'`` (a loose ``EOF`` after it); a system Python process was then found
spinning at 100 % of a core for 15 and 17 hours, each start time matching one runner command to
the second. The mechanism was inferred from those start times, not reproduced.

Denied: (1) an interpreter call (``python``, ``python3``, ``python3.12``, ``py``,
``python.exe``, optionally behind env assignments, ``uv run [opts]``, ``timeout N``, ``env``,
``exec``, ``nohup``) whose first non-option argument is ``-`` and that has no ``<``/``<<``
here-doc/here-string/redirect and is not a later pipeline stage; (2) a heredoc that feeds such an
interpreter line but is never closed. Everything else passes, including ``grep '<<EOF'``,
``python -c 'a << b'``, ``git commit -m "...; python - ..."`` and heredoc bodies: quoted text and
heredoc bodies are blanked before anything is matched.

Known misses (documented, not hidden): a variable as the interpreter (``"$PY" -``), and shell
functions or aliases. Fail-open throughout (any error means allow);
``SHIPWRIGHT_BARE_PYTHON_GUARD=off`` lifts it. Threat model: a forgetful cooperative model, not
an adversary. Cost: one extra ``uv run --no-project`` spawn per Bash call."""

from __future__ import annotations

import json
import os
import re
import sys

_OFF_ENV = "SHIPWRIGHT_BARE_PYTHON_GUARD"

_INTERPRETER = re.compile(r"^(?:.*[\\/])?(?:python[0-9.]*|py)(?:\.exe)?$", re.IGNORECASE)
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
#: Tokens that may stand in front of the interpreter without being a different command.
_WRAPPERS = frozenset({"uv", "run", "env", "exec", "nohup", "nice", "timeout", "then", "do", "else", "{", "(", "time"})
_VALUE_OPTIONS = frozenset({"-X", "-W"})  # python options that swallow the next token
_HEREDOC_OPEN = re.compile(r"""<<(-?)\s*(?:(['"])(?P<q>.+?)\2|(?P<u>[^\s;&|<>()'"]+))""")


def mask(command: str) -> tuple[list[str], list[str]]:
    """Return (lines with quoted text and heredoc bodies blanked, delimiters left unterminated on an interpreter line)."""
    masked: list[str] = []
    pending: list[tuple[str, bool, bool]] = []  # (word, tab-stripped closer, line runs an interpreter)
    quote = ""
    for raw in command.replace("\r\n", "\n").split("\n"):
        if pending:
            word, dash, _ = pending[0]
            if (raw.lstrip("\t") if dash else raw) == word:
                pending.pop(0)
            masked.append("")
            continue
        out: list[str] = []
        opened: list[tuple[str, bool]] = []
        i = 0
        while i < len(raw):
            ch = raw[i]
            if quote:
                if ch == "\\" and quote == '"' and i + 1 < len(raw):
                    out.append("__")
                    i += 2
                    continue
                if ch == quote:
                    quote = ""
                out.append("_")
            elif ch == "\\" and i + 1 < len(raw):
                out.append("  ")
                i += 2
                continue
            elif ch in "'\"":
                quote = ch
                out.append("_")
            elif raw.startswith("$((", i):
                end = raw.find("))", i)
                span = raw[i:] if end < 0 else raw[i:end + 2]
                out.append(" " * len(span))
                i += len(span)
                continue
            elif raw.startswith("<<<", i):
                out.append("<<<")
                i += 3
                continue
            elif raw.startswith("<<", i):
                match = _HEREDOC_OPEN.match(raw, i)
                if match:
                    opened.append((match.group("q") or match.group("u"), match.group(1) == "-"))
                    out.append("<<")
                    i = match.end()
                    continue
                out.append("<<")
                i += 2
                continue
            else:
                out.append(ch)
            i += 1
        line = "".join(out)
        runs_interpreter = _stdin_python(line, check_fed=False)
        for word, dash in opened:
            pending.append((word, dash, runs_interpreter))
        masked.append(line)
    return masked, [word for word, _, interpreter in pending if interpreter]


def _joined(lines: list[str]) -> list[str]:
    """Join a line into the next when it ends in a continuation backslash, ``|``, ``&&`` or ``||``."""
    joined: list[str] = []
    carry = ""
    for line in lines:
        text = carry + line
        stripped = text.rstrip()
        if stripped.endswith(("|", "&&", "||")) or stripped.endswith("\\"):
            carry = stripped.rstrip("\\") + " "
            continue
        carry = ""
        joined.append(text)
    if carry:
        joined.append(carry)
    return joined


def _stdin_python(statement: str, check_fed: bool = True) -> bool:
    """True if some stage of ``statement`` runs ``python -`` and nothing feeds it."""
    for part in re.split(r"&&|\|\||;|&", statement):
        for index, stage in enumerate(part.split("|")):
            if index > 0 or (check_fed and "<" in stage):
                continue
            if _is_stdin_python(stage.split()):
                return True
    return False


def _is_stdin_python(tokens: list[str]) -> bool:
    position = 0
    while position < len(tokens):
        token = tokens[position]
        if _INTERPRETER.match(token):
            break
        if not (_ASSIGNMENT.match(token) or token in _WRAPPERS or token.startswith("-") or token.replace(".", "").isdigit()):
            return False  # a different command (echo, git, grep ...) that merely mentions python
        position += 1
    else:
        return False
    previous = ""
    for token in tokens[position + 1:]:
        if token == "-" and previous not in _VALUE_OPTIONS:
            return True
        if re.match(r"^\d*>", token):
            continue  # an output redirect before the `-` does not feed stdin
        if token.startswith("-") and not token.startswith(("-c", "-m")) and token != "-":
            previous = token
            continue
        if previous in _VALUE_OPTIONS:
            previous = ""
            continue
        return False  # -c / -m / a script path: the program does not come from stdin
    return False


def bare_python_without_input(command: str) -> bool:
    return any(_stdin_python(line) for line in _joined(mask(command)[0]))


def unterminated_heredocs(command: str) -> list[str]:
    return mask(command)[1]


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason + (
            " Use `uv run python - <<'EOF' ... EOF` with a closed heredoc, or `uv run python -c '...'`. "
            f"Only the user can lift this guard ({_OFF_ENV}=off)."),
    }}


def handle_payload(payload: dict) -> dict | None:
    """Decision for one hook payload; ``None`` = take no position (allow)."""
    if os.environ.get(_OFF_ENV, "").strip().lower() in {"off", "0", "false"}:
        return None
    if payload.get("hook_event_name") != "PreToolUse" or payload.get("tool_name") != "Bash":
        return None
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return None
    open_words = unterminated_heredocs(command)
    if open_words:
        return _deny(f"The heredoc delimiter {', '.join(sorted(set(open_words)))} feeding an interpreter is never "
                     "closed, so it would wait on stdin forever.")
    if bare_python_without_input(command):
        return _deny("`python -` has no heredoc, pipe or file behind it, so it would wait on stdin forever.")
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        decision = handle_payload(payload) if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001 -- a hook must never crash the turn
        return 0
    if decision is not None:
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
