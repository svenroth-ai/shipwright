#!/usr/bin/env python3
"""The ratchet that keeps a converted skill converted (deterministic-first programme P12, pilot unit P6).

A converted skill's ``SKILL.md`` keeps the judgement, the questions and one line per outward call; the
mechanics live in code behind one CLI. This gate refuses the way mechanics creep back into the prose. It
reads ``shared/config/converted_skills.json`` and checks the registered skills only:

* **chain** - a fenced shell command joined with ``&&``, ``||``, ``|``, ``;`` or ``&``;
* **multi** - a fenced shell block with more than one command;
* **substitution** - a ``$(...)``, backtick or ``<(...)`` command substitution (double quotes included) the
  skill's ``substitutions`` list does not name;
* **new-command** (second-pass C5) - a fenced shell command whose key (the words before its first flag, for
  example ``uv run {plugin_root}/scripts/release.py prepare``) is not in the skill's ``commands`` list.

A chain or a multi-command block passes only when the registry names that exact block in ``escapes`` (one
escape excuses one block). ``escape_budget`` must equal the number of escapes, so it only falls unless the
registry itself is edited (a reviewed diff, never a prose edit). Known misses (hand-crafted evasions, not
accident protection; a P12 hardening follow-up): FINDINGS D55, e.g. inline code, references/, all after a first flag.

    uv run shared/scripts/tools/check_prompt_mechanics.py --project-root .

Exit codes: 0 clean; 1 findings; 2 the registry or a registered skill is missing, malformed or unreadable.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "config" / "converted_skills.json"
_NON_SHELL_LANGS = {"yaml", "yml", "json", "python", "py", "markdown", "md", "toml", "diff"}
_SHELL_STARTS = ("uv ", "uvx ", "git ", "gh ", "python", "bash ", "sh ", "$ ", "cd ", "export ", "env ", "curl ",
                 "npm ", "npx ", "make ", "./", "rm ", "sudo ")
_ENV_PREFIX = re.compile(r"^[A-Za-z_]\w*=\S*\s+\S")
_FENCE = re.compile(r"^([\s>]*)(`{3,}|~{3,})\s*([^\s`]*)")
_QUOTE = re.compile(r"^\s*>\s?")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.message}"


class RegistryError(Exception):
    """The registry or a registered skill cannot be read (exit 2)."""


def _closes(line: str, fence: str) -> bool:
    bare = line.strip().lstrip("> \t")
    return len(bare) >= len(fence) and set(bare) == {fence[0]}


def fenced_blocks(text: str) -> list[tuple[int, str, list[str]]]:
    """``(line of the opening fence, language, body lines)`` for every fenced block.

    CommonMark: a closer is a line of only the fence character, at least as long as the opener; a fence line
    with an info string never closes. A ``>`` blockquote prefix is read through.
    """
    blocks: list[tuple[int, str, list[str]]] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        start, quoted, fence, lang = i, ">" in m.group(1), m.group(2), m.group(3).lower().strip("{}.")
        body: list[str] = []
        i += 1
        while i < len(lines) and not _closes(lines[i], fence):
            body.append(_QUOTE.sub("", lines[i]) if quoted else lines[i])
            i += 1
        blocks.append((start + 1, lang, body))
        i += 1
    return blocks


def logical_commands(body: list[str]) -> list[str]:
    """One whitespace-normalised string per command: continuations joined, blanks and comments dropped."""
    out: list[str] = []
    pending = ""
    for raw in body:
        line = raw.rstrip()
        if not pending and (not line.strip() or line.lstrip().startswith("#")):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        out.append(" ".join((pending + line).split()))
        pending = ""
    if pending.strip():
        out.append(" ".join(pending.split()))
    return [c[2:] if c.startswith("$ ") else c for c in out]


def is_shell_block(lang: str, body: list[str]) -> bool:
    """Fail closed: every labelled block is shell unless its label is on the non-shell list."""
    if lang:
        return lang not in _NON_SHELL_LANGS
    lines = [ln.strip() for ln in body if ln.strip() and not ln.strip().startswith("#")]
    return any(ln.startswith(_SHELL_STARTS) or _ENV_PREFIX.match(ln) for ln in lines)


def _balanced(command: str, start: int) -> int:
    """Index just past the parenthesis that closes the one opening at ``start`` (or the end)."""
    depth = 0
    for j in range(start, len(command)):
        depth += {"(": 1, ")": -1}.get(command[j], 0)
        if depth == 0:
            return j + 1
    return len(command)


def scan(command: str) -> tuple[list[str], list[str]]:
    """``(operators, substitutions)`` of one command, with one quote and escape model for both.

    Operators count outside quotes; a ``#`` that starts a word ends the command. Substitutions (``$(..)``,
    backticks, and ``<(..)`` / ``>(..)`` outside quotes) count in double quotes too, never in single quotes.
    A backslash outside single quotes escapes the next character. ``2>&1`` and ``&>`` are not chains.
    """
    ops: list[str] = []
    subs: list[str] = []
    single = double = False
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and not single:
            i += 2
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif not single and (command.startswith("$(", i) or (not double and command.startswith(("<(", ">("), i))):
            j = _balanced(command, i + 1)
            subs.append(command[i:j])
            i = j
            continue
        elif not single and ch == "`":
            j = command.find("`", i + 1)
            j = len(command) if j < 0 else j + 1
            subs.append(command[i:j])
            i = j
            continue
        elif not single and not double:
            if ch == "#" and (i == 0 or command[i - 1].isspace()):
                break
            if command.startswith(("&&", "||"), i):
                ops.append(command[i:i + 2])
                i += 1
            elif ch in "|;" or (ch == "&" and command[i - 1:i] != ">" and command[i + 1:i + 2] != ">"):
                ops.append(ch)
        i += 1
    return ops, subs


def command_key(command: str) -> str:
    """The words before the first flag, quotes removed; ``ValueError`` when the line does not parse."""
    words: list[str] = []
    for token in shlex.split(command, comments=True):
        if token.startswith("-"):
            break
        words.append(token)
    return " ".join(words)


def check_skill(entry: dict, text: str) -> tuple[list[Finding], set[int]]:
    """Findings for one registered skill, plus the indices of the escapes its blocks used."""
    path = entry["path"]
    allowed = set(entry.get("commands", []))
    escapes = [list(e["commands"]) for e in entry.get("escapes", [])]
    findings: list[Finding] = []
    used: set[int] = set()
    for line, lang, body in fenced_blocks(text):
        if not is_shell_block(lang, body):
            continue
        commands = logical_commands(body)
        scans = [scan(c) for c in commands]
        chained = [op for ops, _ in scans for op in ops]
        if len(commands) > 1 or chained:
            kind = "chain" if chained else "multi"
            hit = escapes.index(commands) if commands in escapes else -1
            if hit >= 0 and hit not in used:
                used.add(hit)
            elif hit >= 0:
                findings.append(Finding(path, line, "escape-reuse", f"escape {hit} already excuses an earlier block"))
            else:
                what = f"chained with {sorted(set(chained))}" if chained else f"{len(commands)} commands in one block"
                findings.append(Finding(path, line, kind, f"shell block {what}; the mechanics belong in the CLI "
                                        f"(or name this exact block in the registry's escapes)"))
        for command, (_, subs) in zip(commands, scans):
            for sub in subs:
                if sub not in entry.get("substitutions", []):
                    findings.append(Finding(path, line, "substitution",
                                            f"command substitution {sub} is not registered for this skill: {command}"))
            try:
                key = command_key(command)
            except ValueError:
                findings.append(Finding(path, line, "new-command", f"cannot parse: {command}"))
                continue
            if key not in allowed:
                findings.append(Finding(path, line, "new-command",
                                        f"{key!r} is not a registered command of this skill (C5): {command}"))
    return findings, used


def check_registry(registry: dict, root: Path, registry_name: str = DEFAULT_REGISTRY.name) -> list[Finding]:
    findings: list[Finding] = []
    escape_count = 0
    for entry in registry["skills"]:
        skill = root / entry["path"]
        try:
            text = skill.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            raise RegistryError(f"registered skill unreadable: {entry['path']} ({getattr(exc, 'strerror', None) or exc})") from exc
        found, used = check_skill(entry, text)
        findings += found
        escapes = entry.get("escapes", [])
        escape_count += len(escapes)
        findings += [Finding(entry["path"], 0, "stale-escape", f"escape {i} matches no block: {escapes[i]['commands']}")
                     for i in range(len(escapes)) if i not in used]
    if escape_count != registry["escape_budget"]:
        findings.append(Finding(registry_name, 0, "escape-budget",
                                f"{escape_count} escapes but escape_budget is {registry['escape_budget']}: "
                                f"the budget must equal the count (lower it when an escape goes)"))
    return findings


def _strs(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def validate_registry(registry: object) -> None:
    """Explicit shape check; every violation is a ``RegistryError`` (exit 2), never a traceback."""
    def bad(why: str) -> RegistryError:
        return RegistryError(f"malformed registry: {why}")

    if not isinstance(registry, dict) or not isinstance(registry.get("skills"), list):
        raise bad("an object with a 'skills' list is required")
    budget = registry.get("escape_budget")
    if not isinstance(budget, int) or isinstance(budget, bool):
        raise bad("escape_budget must be an integer")
    for entry in registry["skills"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"]:
            raise bad("every skill needs a non-empty string 'path'")
        for key in ("commands", "substitutions"):
            if not _strs(entry.get(key, [])):
                raise bad(f"{entry['path']}: '{key}' must be a list of strings")
        escapes = entry.get("escapes", [])
        if not isinstance(escapes, list):
            raise bad(f"{entry['path']}: 'escapes' must be a list")
        for esc in escapes:
            if not (isinstance(esc, dict) and isinstance(esc.get("reason"), str) and esc["reason"].strip()
                    and _strs(esc.get("commands")) and esc["commands"]):
                raise bad(f"{entry['path']}: each escape needs a non-empty 'reason' and a list of command strings")


def load_registry(path: Path) -> dict:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegistryError(f"registry unreadable: {path} ({exc})") from exc
    validate_registry(registry)
    return registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    args = parser.parse_args(argv)
    try:
        findings = check_registry(load_registry(args.registry), args.project_root, args.registry.name)
    except RegistryError as exc:
        print(f"check_prompt_mechanics: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for finding in findings:
            print(finding.render())
        print(f"check_prompt_mechanics: {len(findings)} finding(s)" if findings
              else "check_prompt_mechanics: converted skills are clean")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
