#!/usr/bin/env python3
"""The ratchet that keeps a converted skill converted (deterministic-first programme P12, pilot unit P6).

A converted skill's ``SKILL.md`` keeps the judgement, the questions and one line per outward call; the
mechanics live in code behind one CLI. This gate refuses the way mechanics creep back into the prose. It
reads ``shared/config/converted_skills.json`` and checks the registered skills only:

* **chain** - a fenced shell command joined with ``&&``, ``||``, ``|`` or ``;``;
* **multi** - a fenced shell block with more than one command;
* **substitution** - a ``$(...)`` or backtick command substitution (double quotes included) the skill's
  ``substitutions`` list does not name;
* **new-command** (second-pass C5) - a fenced shell command whose key (the words before its first flag, for
  example ``uv run {plugin_root}/scripts/release.py prepare``) is not in the skill's ``commands`` list.

A chain or a multi-command block passes only when the registry names that exact block in ``escapes``; the
number of escapes is capped by ``escape_budget`` and an escape that matches no block is itself a finding, so
the budget only ever goes down. The registry is the ratchet: widening it is a reviewed diff, never a prose edit.

    uv run shared/scripts/tools/check_prompt_mechanics.py --project-root .

Exit codes: 0 clean; 1 findings; 2 the registry or a registered skill is missing or unreadable.
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
_SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console", "powershell", "pwsh"}
_SHELL_STARTS = ("uv ", "uvx ", "git ", "gh ", "python", "bash ", "sh ", "$ ")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)")


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


def fenced_blocks(text: str) -> list[tuple[int, str, list[str]]]:
    """``(line of the opening fence, language, body lines)`` for every fenced block."""
    blocks: list[tuple[int, str, list[str]]] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        start, fence, lang = i, m.group(1), m.group(2).lower()
        body: list[str] = []
        i += 1
        while i < len(lines) and lines[i].strip() != fence:
            body.append(lines[i])
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
    if lang:
        return lang in _SHELL_LANGS
    first = next((ln.strip() for ln in body if ln.strip() and not ln.strip().startswith("#")), "")
    return first.startswith(_SHELL_STARTS)


def chain_operators(command: str) -> list[str]:
    """Shell operators outside quotes. ``2>&1`` and ``&>`` redirections are not chains."""
    ops: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif command.startswith(("&&", "||"), i):
            ops.append(command[i:i + 2])
            i += 1
        elif ch in "|;" or (ch == "&" and command[i - 1:i] not in (">", "") and command[i + 1:i + 2] != ">"):
            ops.append(ch)
        i += 1
    return ops


def substitutions(command: str) -> list[str]:
    """Command substitutions (``$(...)`` and backticks) outside single quotes, double quotes included."""
    found: list[str] = []
    single = double = False
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and not single:
            i += 1
        elif ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif not single and command.startswith("$(", i):
            depth, j = 0, i + 1
            while j < len(command):
                depth += {"(": 1, ")": -1}.get(command[j], 0)
                j += 1
                if depth == 0:
                    break
            found.append(command[i:j])
            i = j - 1
        elif not single and ch == "`":
            j = command.find("`", i + 1)
            j = len(command) if j < 0 else j + 1
            found.append(command[i:j])
            i = j - 1
        i += 1
    return found


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
        chained = [op for c in commands for op in chain_operators(c)]
        if len(commands) > 1 or chained:
            kind = "chain" if chained else "multi"
            if commands in escapes:
                used.add(escapes.index(commands))
            else:
                what = f"chained with {sorted(set(chained))}" if chained else f"{len(commands)} commands in one block"
                findings.append(Finding(path, line, kind, f"shell block {what}; the mechanics belong in the CLI "
                                        f"(or name this exact block in the registry's escapes)"))
        for command in commands:
            for sub in substitutions(command):
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
    if escape_count > registry["escape_budget"]:
        findings.append(Finding(registry_name, 0, "escape-budget",
                                f"{escape_count} escapes exceed escape_budget {registry['escape_budget']}"))
    return findings


def load_registry(path: Path) -> dict:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
        registry["escape_budget"]  # noqa: B018 - presence check
        for entry in registry["skills"]:
            assert isinstance(entry["path"], str) and isinstance(entry.get("commands", []), list)
            assert all(isinstance(e["commands"], list) for e in entry.get("escapes", []))
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
        raise RegistryError(f"registry unreadable or malformed: {path} ({exc})") from exc
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
