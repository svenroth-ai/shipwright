#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the architecture rules of the project's stack profile into ``conventions.md``.

    render_architecture_rules.py --project-root R [--profile NAME] [--conventions FILE] [--check]

The profile is ``--profile`` or the ``profile`` of ``shipwright_run_config.json`` (resolved
project > user > bundled, like every phase). The rules go into ONE marked block; running the
tool again replaces that block and nothing else, so a second run on unchanged input changes no
byte. Where the block goes the first time: the unfilled ``{ARCHITECTURE_RULES}`` placeholder of
the conventions template (alone on its line), else directly under an existing ``## Architecture
Rules`` heading (any case), else a new ``## Architecture Rules`` section placed before the first
``## ...Updates`` / ``## Learnings`` section (those sections receive appended bullets, so the block
must not trail them), else at the end. Only the part of the file before adopt's verbatim
``## Imported from`` section is ever searched or edited: the markers, the placeholder and the heading
inside that section are the imported author's text.

A profile that declares no rules (key absent, ``[]``, or a sentinel profile) gets an explicit
"none declared" line. Instruction-only rules are marked as such. A rule with a shape error is
left out and named on stderr; it never fails the run (rule problems are phase-local).

Exit codes: 0 written / unchanged (``--check``: block is current), 1 ``--check`` and the file is
stale, 2 profile cannot be resolved, 3 ``conventions.md`` unusable (missing, or damaged markers),
4 the profile name does not match ``^[a-z0-9][a-z0-9-]*$`` (nothing is resolved or written).
Library use (adopt, which loads this file by path): ``load_rules``, ``render_into(path, profile_name,
rules)`` and ``DamagedMarkers`` (raised for a file whose markers are not exactly one ordered pair).
"""

from __future__ import annotations

import argparse
import os
import re
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ADDED = _SCRIPTS not in sys.path
if _ADDED:
    sys.path.append(_SCRIPTS)  # APPEND, never insert(0): plugins own a `lib` / `tools`
import profile_consumer  # noqa: E402
from profile_model import NAME_RE  # noqa: E402  (the resolver's own profile-name pattern)
from profile_architecture_rules import RuleSet, load_rules  # noqa: E402
if _ADDED:
    sys.path.remove(_SCRIPTS)

BEGIN = "<!-- shipwright:architecture-rules:begin"
END = "<!-- shipwright:architecture-rules:end -->"
HEADING = "## Architecture Rules"
PLACEHOLDER = "{ARCHITECTURE_RULES}"
DEFAULT_CONVENTIONS = ".shipwright/agent_docs/conventions.md"
# Markers count only at the start of a line, so prose that quotes them mid-line is never mistaken for the block.
_BEGIN_RE = re.compile("^" + re.escape(BEGIN), re.MULTILINE)
_END_RE = re.compile("^" + re.escape(END) + r"[ \t\r]*$", re.MULTILINE)
_PLACEHOLDER_RE = re.compile(r"^[ \t]*" + re.escape(PLACEHOLDER) + r"[ \t]*(?=\r?$)", re.MULTILINE)
_HEADING_RE = re.compile(r"^" + re.escape(HEADING) + r"[ \t]*(?=\r?$)", re.MULTILINE | re.IGNORECASE)
_APPEND_BEFORE_RE = re.compile(r"^## [^\n]*(?:Updates|Learnings)[ \t\r]*$", re.MULTILINE)
_IMPORTED_RE = re.compile(r"^## Imported from ", re.MULTILINE)  # adopt's verbatim section: never place the block in it


class DamagedMarkers(ValueError):
    """The begin/end markers in the file do not form exactly one block."""


def _one_line(value: object) -> str:
    """Profile text on one line; comment delimiters neutralised so it cannot close the markers."""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text.replace("<!--", "<!- -").replace("-->", "- ->")


def _how(rule) -> str:
    if rule.legacy or rule.enforcement is None:
        return "instruction only (enforcement class not declared)"
    if rule.lint:
        return f"checked by the linter `{_one_line(rule.lint['tool'])}` (`{_one_line(rule.lint['target'])}`)"
    if rule.mechanism:
        paths = ", ".join(f"`{_one_line(p)}`" for p in rule.mechanism)
        return f"{_one_line(rule.enforcement)}: {paths}"
    return "instruction only (" + _one_line(rule.enforcement).removeprefix("prompt-only (").removesuffix(")") + ")"


def render_block(profile_name: str, rules: RuleSet) -> str:
    """The marked block, newline-terminated, LF line endings."""
    name = _one_line(profile_name)
    head = (f"{BEGIN} (generated from stack profile `{name}` by render_architecture_rules.py; "
            "edit the profile, not this block) -->")
    body = []
    if not rules.rules and not rules.errors:
        body = [f"_No architecture rules declared by stack profile `{name}`._"]
    if rules.errors:  # an invalid declaration must not read as "none declared"
        body.append(f"_{len(rules.errors)} architecture rule problem(s) in stack profile `{name}`; the affected "
                    f"rules are not listed. Run `resolve_profile.py validate --name {name}` to see them._")
    for rule in rules.rules:
        line = f"- **{_one_line(rule.id)}** - {_one_line(rule.text)}"
        if rule.why:
            line += f" Why: {_one_line(rule.why)}"
        line += f" How it is kept: {_how(rule)}."
        if rule.note:
            line += f" Note: {_one_line(rule.note)}"
        body.append(line)
    return "\n".join([head, *body, END]) + "\n"


def apply_block(text: str, block: str) -> str:
    """``text`` with the block replaced (or placed the first time). Raises DamagedMarkers."""
    nl = "\r\n" if "\r\n" in text else "\n"
    block = block.rstrip("\n").replace("\n", nl)
    imported = _IMPORTED_RE.search(text)
    cut = imported.start() if imported else len(text)
    head, rest = text[:cut], text[cut:]
    begins, ends = list(_BEGIN_RE.finditer(head)), list(_END_RE.finditer(head))
    if len(begins) != len(ends) or len(begins) > 1 or (begins and begins[0].start() > ends[0].start()):
        raise DamagedMarkers(
            f"expected zero or one begin/end marker pair, found {len(begins)} begin and {len(ends)} end")
    if begins:
        return head[:begins[0].start()] + block + head[ends[0].start() + len(END):] + rest
    placeholder = _PLACEHOLDER_RE.search(head)
    if placeholder:
        return head[:placeholder.start()] + block + head[placeholder.end():] + rest
    heading = _HEADING_RE.search(head)
    if heading:
        tail = head[heading.end():] + rest
        return head[:heading.end()] + nl + nl + block + (tail or nl)
    section = f"{HEADING}{nl}{nl}{block}{nl}{nl}"
    appended = _APPEND_BEFORE_RE.search(head)
    if appended:  # before the sections that receive appended bullets
        return head[:appended.start()] + section + head[appended.start():] + rest
    return head.rstrip("\r\n") + nl + nl + section.rstrip("\r\n") + nl + (nl + rest if rest else "")


def render_into(path: str, profile_name: str, rules: RuleSet, *, write: bool = True) -> bool:
    """Apply the block to ``path``; True when the file changed (or would change)."""
    with open(path, encoding="utf-8", newline="") as fh:
        old = fh.read()
    new = apply_block(old, render_block(profile_name, rules))
    if new == old:
        return False
    if write:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
    return True


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="render_architecture_rules.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--profile")
    ap.add_argument("--conventions")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 when the block is stale")
    args = ap.parse_args(argv)
    path = args.conventions or os.path.join(args.project_root, DEFAULT_CONVENTIONS)
    try:
        name = args.profile if args.profile is not None else profile_consumer.config_profile(args.project_root)
        if name is None or (name == "" and args.profile is None):
            raise ValueError("no profile: pass --profile or set `profile` in shipwright_run_config.json")
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):  # the name may reach an agent's shell command
            sys.stderr.write(f"error: invalid profile name {str(name)[:60]!r}: it must match {NAME_RE.pattern} "
                             "(lowercase letters, digits, '-'); nothing was resolved or written\n")
            return 4
        res = profile_consumer.resolve_named(name, args.project_root, origin="--profile" if args.profile else None)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"error: profile cannot be loaded: {type(exc).__name__}: {exc}\n")
        return 2
    rules = load_rules(res.data.get("architecture_rules"))
    for msg in rules.errors:
        sys.stderr.write(f"warning: architecture_rules: {msg} (left out of the block)\n")
    for msg in rules.warnings:
        sys.stderr.write(f"warning: architecture_rules: {msg}\n")
    try:
        changed = render_into(path, res.name, rules, write=not args.check)
    except (OSError, UnicodeError, DamagedMarkers) as exc:
        sys.stderr.write(f"error: {path}: {exc}\n")
        return 3
    except Exception as exc:  # noqa: BLE001 - exit 1 under --check must only ever mean stale
        sys.stderr.write(f"error: {path}: {type(exc).__name__}: {exc}\n")
        return 3
    sys.stdout.write(f"{'stale' if args.check and changed else 'updated' if changed else 'unchanged'}: {path}\n")
    return 1 if (args.check and changed) else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    sys.exit(_main())
