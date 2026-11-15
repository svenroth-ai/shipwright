"""Architecture rules of a stack profile: the rule object, its shape check and the loader.

Frozen contract (consumed by the render tool, the template and profile units that follow):

``architecture_rules`` is absent / null (not declared), ``[]`` (explicitly none) or a list
whose items are rule objects or, for the legacy format, plain sentences (mixed lists are
accepted). A rule object has ``id`` (unique, ``^[a-z0-9][a-z0-9-]*$``), ``text``, ``why``,
``enforcement`` (closed vocabulary below), at most one of ``lint`` and ``mechanism``, and
an optional ``note``. ``lint`` is ``{tool, target, block}``; ``mechanism`` is a non-empty
list of repo-relative paths. Which enforcement class may carry what is ``ALLOWED``.

A legacy sentence becomes a rule with id ``legacy-string-<position>``, ``legacy=True`` and
``enforcement=None``, which means "instruction only, class undeclared" (a renderer treats
it as instruction-only). The legacy format is accepted through the end of the
profile-architecture-rules campaign, when the last bundled profile using it is converted.

``lint.block`` shape per tool: ``eslint`` = a flat-config object that has a non-empty ``rules``
object (``files`` / ``ignores`` allowed beside it); ``ruff`` = a non-empty object of keys under
``[tool.ruff.lint]`` (finer checking waits for the first ruff-backed rule). Base directories:
``mechanism`` paths are relative to the Shipwright repo for a bundled profile and to the project
root for any other; ``lint.target`` is always relative to the target project (only containment
is checked, never existence). A wrong top-level type is an error, yields no rules and counts
as "not declared"; unknown rule keys (not starting with ``_``) are warnings.

Order: declared objects keep their profile order; legacy sentences follow them (a declared id
beats a generated one), so a renderer must not assume positional fidelity in a mixed list.

Errors are rule-local: a rule with a shape error is left out of ``RuleSet.rules`` and named
in ``RuleSet.errors``; the other rules and the profile stay usable. Nothing here raises for
a wrong-shaped value. ``check_paths`` is a point-in-time filesystem check (the tree can
change afterwards) and returns the rule ids that have a path problem: a consumer that
executes a mechanism skips those ids.

``ENFORCEMENT`` is a deliberate copy of ``lib.constitution_register.ENFORCEMENT`` (profiles
must not import the constitution's library). A drift test is the only guard that keeps the
two equal: change both sides together.

Stdlib-only. The D2 hot-file rule of ``profile_resolver`` does not cover this module.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

ENFORCEMENT = (
    "hook",
    "validator",
    "test",
    "prompt-only (mechanisable)",
    "prompt-only (judgement)",
    "unimplemented",
)
LINT_TOOLS = ("eslint", "ruff")
# enforcement class -> what it may (and for hook/test/validator must) carry
ALLOWED = {
    "validator": ("lint", "mechanism"),
    "hook": ("mechanism",),
    "test": ("mechanism",),
    "prompt-only (mechanisable)": (),
    "prompt-only (judgement)": (),
    "unimplemented": (),
}
NOTE_REQUIRED = ("prompt-only (mechanisable)", "unimplemented")
_KEYS = ("id", "text", "why", "enforcement", "lint", "mechanism", "note")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass
class Rule:
    id: str
    text: str
    why: str = ""
    enforcement: str | None = None
    lint: dict | None = None
    mechanism: list | None = None
    note: str = ""
    legacy: bool = False


@dataclass
class RuleSet:
    rules: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    declared: bool = False  # False: key absent, null or of the wrong type


def bad_path(value: object) -> str | None:
    """Why ``value`` is not a repo-relative path, or None."""
    if not isinstance(value, str) or not value.strip():
        return "must be a non-empty string"
    if value.startswith(("/", "\\")) or _DRIVE_RE.match(value):
        return "must be relative, not absolute"
    if "\\" in value or "\x00" in value:
        return "must use forward slashes only"
    if any(seg in ("", ".", "..") for seg in value.split("/")):
        return "must not contain empty, '.' or '..' segments"
    return None


def _text(obj: dict, key: str):
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        return f"'{key}' must be a non-empty string"
    return None


def _lint_problem(lint: object) -> str | None:
    if not isinstance(lint, dict):
        return "'lint' must be an object {tool, target, block}"
    if lint.get("tool") not in LINT_TOOLS:
        return f"lint.tool must be one of {', '.join(LINT_TOOLS)}"
    why = bad_path(lint.get("target"))
    if why:
        return f"lint.target {why}"
    block = lint.get("block")
    if not isinstance(block, dict) or not block:
        return "lint.block must be a non-empty object"
    if lint["tool"] == "eslint" and not (isinstance(block.get("rules"), dict) and block["rules"]):
        return "lint.block for eslint must hold a non-empty 'rules' object"
    return None


def _object_problem(obj: dict) -> str | None:
    for key in ("text", "why"):
        msg = _text(obj, key)
        if msg:
            return msg
    if obj.get("note") is not None and not isinstance(obj["note"], str):
        return "'note' must be a string"
    enf = obj.get("enforcement")
    if enf not in ENFORCEMENT:
        return f"enforcement {enf!r} is not one of: {', '.join(ENFORCEMENT)}"
    has_lint, has_mech = obj.get("lint") is not None, obj.get("mechanism") is not None
    if has_lint and has_mech:
        return "a rule carries 'lint' or 'mechanism', never both"
    allowed = ALLOWED[enf]
    if has_lint and "lint" not in allowed:
        return f"'lint' is only valid with enforcement 'validator', not {enf!r}"
    if has_mech and "mechanism" not in allowed:
        return f"'mechanism' is not valid with enforcement {enf!r}"
    if allowed and not (has_lint or has_mech):
        return f"enforcement {enf!r} needs {' or '.join(repr(a) for a in allowed)}"
    if has_lint and (msg := _lint_problem(obj["lint"])):
        return msg
    if has_mech:
        mech = obj["mechanism"]
        if not isinstance(mech, list) or not mech:
            return "'mechanism' must be a non-empty list of paths"
        for path in mech:
            if why := bad_path(path):
                return f"mechanism entry {path!r} {why}"
    if enf in NOTE_REQUIRED and not (obj.get("note") or "").strip():
        return f"enforcement {enf!r} needs a 'note' saying why it is not enforced"
    return None


def load_rules(raw: object) -> RuleSet:
    """Normalise ``architecture_rules``; never raises."""
    out = RuleSet()
    if raw is None:
        return out
    if not isinstance(raw, list):
        out.errors.append(f"must be a list, not {type(raw).__name__}")
        return out
    out.declared = True
    seen: dict = {}
    claimed: set = set()  # every well-formed id, valid rule or not: the first use owns it
    legacy = []
    for pos, item in enumerate(raw, 1):
        if isinstance(item, str):
            if item.strip():
                legacy.append(Rule(f"legacy-string-{pos}", item, legacy=True))
            else:
                out.errors.append(f"rule {pos}: a legacy sentence must not be empty")
            continue
        if not isinstance(item, dict):
            out.errors.append(f"rule {pos}: must be an object or a legacy sentence")
            continue
        rid = item.get("id")
        label = rid if isinstance(rid, str) and rid else f"#{pos}"
        if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
            out.errors.append(f"rule {label}: 'id' must match {ID_RE.pattern}")
        elif rid in claimed:
            out.errors.append(f"rule {rid}: duplicate id (first use wins)")
        elif problem := _object_problem(item):
            claimed.add(rid)
            out.errors.append(f"rule {rid}: {problem}")
        else:
            claimed.add(rid)
            extra = sorted(k for k in item if k not in _KEYS and not str(k).startswith("_"))
            if extra:
                out.warnings.append(f"rule {rid}: unknown key(s) {', '.join(map(repr, extra))} ignored")
            seen[rid] = Rule(rid, item["text"], item["why"], item["enforcement"],
                             item.get("lint"), item.get("mechanism"), item.get("note") or "")
            out.rules.append(seen[rid])
    for rule in legacy:  # after the objects: a declared id always beats a generated one
        if rule.id in claimed:
            out.errors.append(f"rule {rule.id}: legacy sentence collides with a declared id and is dropped")
        else:
            out.rules.append(rule)
    if legacy:
        out.warnings.append(
            f"uses the old plain-sentence format ({len(legacy)} rule(s)); "
            "convert each to a rule object (id, text, why, enforcement) - see docs/stack-profiles.md"
        )
    return out


def check_paths(rules: list, root: str | os.PathLike) -> list:
    """``[(rule_id, message)]`` for paths that leave ``root`` or (mechanisms) do not exist.

    Point-in-time only: realpath resolves symlinks and junctions now; nothing is guaranteed
    afterwards. A lint target is only checked for containment (the scaffold writes it).
    """
    base = os.path.realpath(os.fspath(root))
    problems = []
    for rule in rules:
        targets = [(p, True) for p in rule.mechanism or []]
        if rule.lint:
            targets.append((rule.lint["target"], False))
        for rel, must_exist in targets:
            real = os.path.realpath(os.path.join(base, rel))
            try:
                inside = os.path.commonpath([os.path.normcase(real), os.path.normcase(base)]) == os.path.normcase(base)
            except ValueError:
                inside = False
            if not inside:
                problems.append((rule.id, f"path {rel!r} resolves outside the project root"))
            elif must_exist and not os.path.exists(real):
                problems.append((rule.id, f"mechanism {rel!r} does not exist"))
    return problems


def shadow_rules_warning(data: dict, shadows: list, bundled_dir: str) -> str | None:
    """Warn when a custom profile that shadows a bundled one declares no rules, but the
    bundled one has some. ``[]`` is an explicit choice and is not warned about."""
    if data.get("architecture_rules") is not None:
        return None
    here = os.path.realpath(bundled_dir)
    for path in shadows:
        if os.path.realpath(os.path.dirname(path)) != here:
            continue
        try:
            with open(path, encoding="utf-8-sig") as fh:
                bundled = json.load(fh).get("architecture_rules")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(bundled, list) and bundled:
            return (f"WARNING: this profile declares no architecture_rules, but the bundled profile "
                    f"it shadows declares {len(bundled)}; copy them in or set \"architecture_rules\": [] on purpose.")
    return None
