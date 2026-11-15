"""Constitution enforcement register: the rules of ``shared/constitution.md`` and the declaration of how each is enforced.

The constitution is prose. This module reads it into rule units and checks them against the register in
``shared/config/conventions.json`` (section ``constitution``). The register answers one question per rule,
"enforced how?", and the drift test built on this module fails when a rule has no answer. It never judges
whether a rule is *followed*: a rule that needs judgement is recorded as such, not turned into a gate.

A rule unit is one bullet of ALWAYS / ASK FIRST / NEVER, one numbered pre-phase principle, one row of the
escalation or test-layer table, or one of the two blocks of the AskUserQuestion discipline.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

ENFORCEMENT = (
    "hook",
    "validator",
    "test",
    "prompt-only (mechanisable)",
    "prompt-only (judgement)",
    "unimplemented",
)
TIERS = ("pre-phase", "always", "ask-first", "never", "escalation", "test-layer", "question-discipline")
_SECTION_TIER = (
    ("Pre-Phase Principles", "pre-phase"),
    ("ALWAYS", "always"),
    ("ASK FIRST", "ask-first"),
    ("NEVER", "never"),
    ("Escalation Thresholds", "escalation"),
    ("Test Layer Boundaries", "test-layer"),
    ("Tool Call Discipline", "question-discipline"),
)
# the AskUserQuestion section is prose, so its two rules are cut at these opening lines
_BLOCK_STARTS = ("After calling AskUserQuestion", "User-facing decision questions MUST")
_BLOCK_ENDS = ("Rationale:", "**When to use")
_NON_RULE_HEADINGS = ("Programmatic Enforcement",)  # prose about enforcement, not rules
_LIST_TIERS = ("pre-phase", "always", "ask-first", "never")


@dataclass(frozen=True)
class Rule:
    tier: str
    text: str

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:12]


def _norm(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(line.strip() for line in lines)).strip()


def _tier_of(heading: str) -> str | None:
    return next((tier for prefix, tier in _SECTION_TIER if heading.startswith(prefix)), None)


def parse_rules(text: str) -> list[Rule]:
    """Every rule unit of the constitution, in document order."""
    return parse(text)[0]


def parse(text: str) -> tuple[list[Rule], list[str]]:
    """The rule units plus the lines the parser could not place.

    A line it cannot place is text a reword could change without moving any hash, and a ``##`` heading that is
    neither a known tier nor known non-rule prose would hold rules nobody declared; both are reported so the
    drift test fails instead of passing over them.
    """
    rules: list[Rule] = []
    strays: list[str] = []
    tier: str | None = None
    current: list[str] | None = None
    in_block = False
    table_rows_seen = 0

    def close() -> None:
        nonlocal current
        if current and tier:
            rules.append(Rule(tier, _norm(current)))
        current = None

    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw.startswith("## "):
            close()
            in_block = False
            table_rows_seen = 0
            heading = raw[3:].strip()
            tier = _tier_of(heading)
            if tier is None and not heading.startswith(_NON_RULE_HEADINGS):
                strays.append(f"unknown section heading: {raw.strip()}")
            continue
        if tier is None:
            continue
        if tier == "question-discipline":
            if raw.startswith(_BLOCK_STARTS):
                close()
                current, in_block = [raw], True
            elif in_block and raw.startswith(_BLOCK_ENDS):
                close()
                in_block = False
            elif in_block:
                current.append(raw)  # type: ignore[union-attr]
            continue
        if tier in ("escalation", "test-layer"):
            if raw.startswith("|"):
                table_rows_seen += 1
                if table_rows_seen > 2:  # the header and the separator are not rules
                    cells = [c.strip() for c in raw.strip().strip("|").split("|")]
                    rules.append(Rule(tier, " | ".join(cells)))
            continue
        starts = re.match(r"^\d+\. \*\*", raw) if tier == "pre-phase" else raw.startswith("- ")
        if starts:
            close()
            current = [raw]
        elif current is not None and raw.startswith("  ") and raw.strip():
            current.append(raw)
        elif not raw.strip() or raw.startswith(("---", ">")):
            close()
        elif tier in _LIST_TIERS:
            strays.append(f"[{tier}] unplaced line: {raw.strip()[:80]}")
    close()
    return rules, strays


def load_register(conventions_path: Path) -> list[dict]:
    data = json.loads(conventions_path.read_text(encoding="utf-8"))
    return data["sections"]["constitution"]["rules"]


def _hook_files(repo_root: Path) -> set[str]:
    """Basenames of every script named in a plugin's hooks.json: a hook entry must be one that is registered."""
    names: set[str] = set()
    for hooks_json in repo_root.glob("plugins/*/hooks/hooks.json"):
        names.update(re.findall(r"([\w.-]+\.(?:py|sh))", hooks_json.read_text(encoding="utf-8")))
    return names


def check(rules: list[Rule], register: list[dict], repo_root: Path, strays: list[str] | None = None) -> list[str]:
    """One line per drift. Empty when every rule is declared and every declaration still matches a rule."""
    problems: list[str] = list(strays or [])
    by_hash = {r.text_hash: r for r in rules}
    seen: dict[str, int] = {}
    for r in rules:
        seen[r.text_hash] = seen.get(r.text_hash, 0) + 1
    problems += [f"two rules have the same text (hash {h}); one declaration cannot cover both" for h, n in seen.items() if n > 1]
    declared = {}
    registered = _hook_files(repo_root)
    for entry in register:
        missing = [k for k in ("id", "tier", "text_hash", "enforcement") if k not in entry]
        if missing:
            problems.append(f"entry {entry.get('id', entry)!r} lacks {', '.join(missing)}")
            continue
        eid = entry["id"]
        if entry.get("enforcement") not in ENFORCEMENT:
            problems.append(f"{eid}: enforcement {entry.get('enforcement')!r} is not in the closed vocabulary")
        if entry.get("tier") not in TIERS:
            problems.append(f"{eid}: tier {entry.get('tier')!r} is unknown")
        if entry["text_hash"] in declared:
            problems.append(f"{eid}: text_hash {entry['text_hash']} is declared twice (also {declared[entry['text_hash']]})")
        declared[entry["text_hash"]] = eid
        if entry["text_hash"] not in by_hash:
            problems.append(f"{eid}: no rule has text_hash {entry['text_hash']} any more (reworded or removed) - re-declare it")
        elif by_hash[entry["text_hash"]].tier != entry.get("tier"):
            problems.append(f"{eid}: declared as tier {entry.get('tier')!r} but the rule is in {by_hash[entry['text_hash']].tier!r}")
        mech = entry.get("mechanism") or []
        if entry.get("enforcement") in ("hook", "validator", "test") and not mech:
            problems.append(f"{eid}: enforcement {entry['enforcement']} names no mechanism")
        for path in mech:
            if Path(path).is_absolute() or ".." in Path(path).parts:
                problems.append(f"{eid}: mechanism {path} must be a repo-relative path")
            elif not (repo_root / path).exists():
                problems.append(f"{eid}: mechanism {path} does not exist")
        if entry["enforcement"] == "hook" and mech and not any(Path(m).name in registered for m in mech):
            problems.append(f"{eid}: none of its mechanisms is registered in a plugin hooks.json")
    ids = [e.get("id") for e in register]
    problems += [f"id {i} is used twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for rule in rules:
        if rule.text_hash not in declared:
            problems.append(f"undeclared rule [{rule.tier}] {rule.text_hash}: {rule.text[:90]}")
    return problems


def render_markdown(register: list[dict]) -> str:
    """The generated register document. The only hand-written part is the JSON it comes from."""
    lines = [
        "# Constitution enforcement register",
        "",
        "> GENERATED from `shared/config/conventions.json` (section `constitution`) by",
        "> `shared/scripts/tools/constitution_register.py --write`. Edit the JSON, never this file.",
        "> It says, per rule of `shared/constitution.md`, how the rule is enforced. A rule that needs judgement",
        "> is recorded as such; this register never turns judgement into a gate and carries no coverage number.",
        "",
    ]
    for tier in TIERS:
        rows = [e for e in register if e["tier"] == tier]
        if not rows:
            continue
        lines += [f"## {tier} ({len(rows)})", "", "| id | enforcement | mechanism | note |", "|---|---|---|---|"]
        for e in rows:
            mech = "<br>".join(f"`{m}`" for m in e.get("mechanism") or []) or "-"
            note = (e.get("note") or "").replace("|", "\\|")
            lines.append(f"| `{e['id']}` | {e['enforcement']} | {mech} | {note} |")
        lines.append("")
    return "\n".join(lines)
