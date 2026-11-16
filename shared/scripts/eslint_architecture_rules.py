"""Check and (re)apply the ESLint fragments of a stack profile's architecture rules.

A profile rule of class ``validator`` can carry ``lint = {tool: "eslint", target, block}``.
/shipwright-project step 7 writes the blocks into the project's flat ESLint config between
marker comments::

    // BEGIN architecture-rule: <id>
      { ...the profile's block, as JSON... },
    // END architecture-rule: <id>

The Next.js app is created later, by the build phase, and create-next-app writes its own
config, so the blocks can be lost without a sound. This module is the deterministic part of
getting them back:

``check``  - per rule: ``ok`` | ``missing`` | ``stale`` (block differs from the profile) |
             ``unpaired`` (a begin without an end, a duplicate, wrong order) |
             ``outside`` (block sits beyond the exported array, so it is dead text) |
             ``shadowed`` (config code follows the last block and can override its rules).
             Marker/content checks need no parsing; the two position checks run only when the
             exported array is recognised and are skipped otherwise. It does NOT prove ESLint
             loads the file or that a rule is not switched off by other means (known limit).
``apply``  - appends missing blocks as the LAST elements of the exported array (a later flat-config
             object that sets the same rule wins), found with the comment/string-aware lexer.
             It refuses anything that is not plainly ``export default [...]``,
             ``export default defineConfig([...])``, ``module.exports = [...]`` or a named
             const of those; the result is re-checked before a byte is written. A stale block is
             replaced only with ``replace_stale`` (the scaffold step asks first); unpaired markers
             are never touched. No config and no legacy ``.eslintrc*``: the shipped template is
             written when it carries every rule of the profile.

Never edits package.json (it only notes missing dev dependencies). Stdlib-only.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import profile_consumer
from _ts_lexer import lex
from _eslint_config_splice import array_bounds, insert_blocks, live_in_array
from profile_architecture_rules import Rule, load_rules

CONFIG_NAMES = ("eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
                "eslint.config.ts", "eslint.config.mts", "eslint.config.cts")  # ESLint's own lookup order
TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "eslint" / "eslint.config.mjs.template"
_MARK = re.compile(r"^[ \t]*// (BEGIN|END) architecture-rule: ([a-z0-9][a-z0-9-]*)[ \t]*\r?$", re.M)
_RESTRICT = re.compile(r"no-restricted-(?:imports|globals|properties)")
_DEPS = ("eslint", "typescript-eslint", "typescript")


@dataclass
class Finding:
    rule_id: str
    status: str  # ok | missing | stale | unpaired | outside | shadowed
    detail: str = ""


@dataclass
class Report:
    config: str | None = None  # file name inside the project root
    findings: list = field(default_factory=list)
    legacy: list = field(default_factory=list)  # .eslintrc* files found
    notes: list = field(default_factory=list)

    @property
    def bad(self) -> list:
        return [f for f in self.findings if f.status != "ok"]


@dataclass
class Applied:
    status: str  # unchanged | applied | cannot
    message: str = ""
    report: Report | None = None


def eslint_rules(rules: list) -> list:
    """The rules of a profile that carry an ESLint fragment."""
    return [r for r in rules if isinstance(r, Rule) and r.lint and r.lint.get("tool") == "eslint"]


def render_fragment(rule: Rule) -> str:
    """One marked block exactly as the template carries it (LF, two-space indent, trailing comma)."""
    body = "\n".join("  " + line for line in json.dumps(rule.lint["block"], indent=2).split("\n"))
    return f"  // BEGIN architecture-rule: {rule.id}\n{body},\n  // END architecture-rule: {rule.id}\n"


def _markers(text: str) -> dict:
    out: dict = {}
    for m in _MARK.finditer(text):
        out.setdefault(m.group(2), {"BEGIN": [], "END": []})[m.group(1)].append(m)
    return out


def _span(marks: dict | None):
    """(begin_match, end_match) when exactly one ordered pair, else None."""
    if not marks or len(marks["BEGIN"]) != 1 or len(marks["END"]) != 1:
        return None
    begin, end = marks["BEGIN"][0], marks["END"][0]
    return (begin, end) if begin.start() < end.start() else None


def inspect(text: str, rules: list) -> list:
    marks = _markers(text)
    out = []
    bounds, _why = array_bounds(text)  # None: shape not recognised, the position checks are skipped
    for rule in rules:
        if rule.id not in marks:
            out.append(Finding(rule.id, "missing", "no marker block for this rule"))
            continue
        span = _span(marks[rule.id])
        if span is None:
            out.append(Finding(rule.id, "unpaired", "begin/end markers are not exactly one ordered pair"))
            continue
        body = text[span[0].end():span[1].start()].strip().removesuffix(",")
        try:
            same = json.loads(body) == rule.lint["block"]
        except ValueError:
            same = False
        out.append(Finding(rule.id, "ok" if same else "stale",
                           "" if same else "block differs from the profile's fragment"))
        live = (live_in_array(text, bounds, span[0].start(), span[1].end()) if bounds is not None
                else bool(lex(text).code_only[span[0].start():span[1].end()].strip()))  # at least not a comment
        if not live:
            out[-1] = Finding(rule.id, "outside", "the block is commented out or not inside the exported config array")
    ends = [(_span(marks[r.id])[1].end(), i) for i, r in enumerate(rules) if r.id in marks and _span(marks[r.id])]
    if bounds is not None and ends:
        last_end, idx = max(ends)
        tail = lex(text).code_only[last_end:bounds[1]].strip(" \t\r\n,")
        if last_end <= bounds[1] and tail and out[idx].status == "ok":
            out[idx] = Finding(rules[idx].id, "shadowed", "config code after the last block can override its rules")
    return out


def find_config(root: str | os.PathLike) -> tuple:
    """(the config file ESLint picks first, or None; [legacy .eslintrc* names])."""
    base = Path(root)
    config = next((n for n in CONFIG_NAMES if (base / n).is_file()), None)
    legacy = sorted(p.name for p in base.glob(".eslintrc*") if p.is_file())
    return config, legacy


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _is_workspace(root: Path) -> bool:
    try:
        pkg = json.loads(_read(root / "package.json"))
    except (OSError, ValueError):
        return False
    return isinstance(pkg, dict) and bool(pkg.get("workspaces"))


def _dep_notes(root: Path) -> list:
    try:
        pkg = json.loads(_read(root / "package.json"))
    except (OSError, ValueError):
        return []
    have = set(pkg.get("dependencies") or {}) | set(pkg.get("devDependencies") or {}) if isinstance(pkg, dict) else set()
    gone = [d for d in _DEPS if d not in have]
    return [f"package.json lacks devDependencies: {', '.join(gone)} (the template needs them)"] if gone else []


def check(root: str | os.PathLike, rules: list) -> Report:
    rules = eslint_rules(rules)
    name, legacy = find_config(root)
    rep = Report(config=name, legacy=legacy)
    rep.notes.extend(_dep_notes(Path(root)))
    extra = [n for n in CONFIG_NAMES if (Path(root) / n).is_file()][1:]
    if extra:
        rep.notes.append(f"more than one eslint.config.* exists; ESLint uses {name}, the others are ignored: {', '.join(extra)}")
    if name is None:
        why = ("only a legacy .eslintrc* exists (flat config would replace its rules)" if legacy
               else "no eslint.config.* in the project root")
        rep.findings = [Finding(r.id, "missing", why) for r in rules]
        return rep
    text = _read(Path(root) / name)
    rep.findings = inspect(text, rules)
    rep.notes.extend(_notes(text))
    return rep


def _replace_stale(text: str, rules: list, stale: set) -> str:
    marks = _markers(text)
    nl = "\r\n" if "\r\n" in text else "\n"
    for rule in reversed([r for r in rules if r.id in stale]):  # later spans first: offsets stay valid
        begin, end = _span(marks[rule.id])
        stop = end.end() - (1 if text[end.end() - 1:end.end()] == "\r" else 0)  # keep the line's own CR
        text = text[:begin.start()] + render_fragment(rule).rstrip("\n").replace("\n", nl) + text[stop:]
        marks = _markers(text)
    return text


def _write(path: Path, text: str) -> str:
    """"" when written (atomic replace), else why not; a symlinked config is never replaced by a regular file."""
    if path.is_symlink():
        return f"{path.name} is a symlink; edit its target by hand"
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        return f"could not write {path.name}: {exc}"
    return ""


def _notes(text: str) -> list:
    notes = []
    if "parser" not in text and "typescript-eslint" not in text and "eslint-config-next" not in text:
        notes.append("no typescript parser seen in the config; allowTypeImports needs the typescript-eslint parser")
    return notes


def _outside_blocks(text: str) -> str:
    """The config text without the paired marker blocks (what the project itself wrote)."""
    spans = sorted((sp[0].start(), sp[1].end()) for sp in (_span(m) for m in _markers(text).values()) if sp)
    out, pos = [], 0
    for begin, end in spans:
        out.append(text[pos:begin])
        pos = end
    out.append(text[pos:])
    return "".join(out)


def apply(root: str | os.PathLike, rules: list, *, replace_stale: bool = False) -> Applied:
    rules = eslint_rules(rules)
    base = Path(root)
    rep = check(root, rules)
    if not rules or not rep.bad:
        return Applied("unchanged", "all rule blocks are present", rep)
    if any(f.status == "unpaired" for f in rep.findings):
        return Applied("cannot", "markers are damaged (begin without end, duplicate or wrong order); fix them by hand", rep)
    if rep.config is None:
        if rep.legacy:
            return Applied("cannot", "only a legacy .eslintrc* exists; writing a flat config next to it would replace its rules", rep)
        text = _read(TEMPLATE) if TEMPLATE.is_file() else ""
        if not text or any(f.status != "ok" for f in inspect(text, rules)):
            return Applied("cannot", "the shipped ESLint template does not carry every rule of this profile", rep)
        if _is_workspace(base):
            return Applied("cannot", "package.json declares workspaces: the app's own folder needs the config, not the root", rep)
        if bad_write := _write(base / "eslint.config.mjs", text):
            return Applied("cannot", bad_write, rep)
        return Applied("applied", "wrote eslint.config.mjs from the shipped template", check(root, rules))
    path = base / rep.config
    text = _read(path)
    if any(f.status == "missing" for f in rep.findings) and _RESTRICT.search(_outside_blocks(text)):
        # an appended block replaces the options of an earlier object for the same rule: that is the
        # scaffold step's fold decision (3c), not something to guess
        return Applied("cannot", f"{rep.config} already sets no-restricted-imports/globals/properties; "
                                 "folding its options into the blocks needs a decision (project step 7, 3c)", rep)
    stale = {f.rule_id for f in rep.findings if f.status == "stale"}
    if stale and replace_stale:
        text = _replace_stale(text, rules, stale)
    missing = [r for r in rules if r.id in {f.rule_id for f in rep.findings if f.status == "missing"}]
    if not missing and not (stale and replace_stale):
        kinds = ", ".join(sorted({f.status for f in rep.bad}))
        if kinds in ("stale", "shadowed", "shadowed, stale"):  # deliberate edits (step 7, 3c): left alone, still reported
            return Applied("unchanged", f"{rep.config}: {kinds} block(s) left alone on purpose (replace_stale overwrites)", rep)
        return Applied("cannot", f"{rep.config}: {kinds} blocks need a hand edit", rep)
    if missing:
        text, why = insert_blocks(text, [render_fragment(r) for r in missing])
        if text is None:
            return Applied("cannot", f"{rep.config}: {why}; add the blocks by hand from the profile", rep)
    leftover = [f for f in inspect(text, rules) if f.status in ("missing", "unpaired", "outside")]
    if leftover:  # never write a result that does not verify
        return Applied("cannot", f"{rep.config}: the merged result did not verify; nothing was written", rep)
    if bad_write := _write(path, text):
        return Applied("cannot", bad_write, rep)
    after = check(root, rules)
    return Applied("applied", f"updated {rep.config}", after)


def rules_for_project(root: str | os.PathLike, profile: str | None = None, *, quiet: bool = False) -> tuple:
    """(profile name, [Rule with an eslint fragment]); ValueError when the profile cannot be resolved."""
    name = profile or profile_consumer.config_profile(str(root))
    if not name:
        raise ValueError("no profile: pass one or set `profile` in shipwright_run_config.json")
    res = profile_consumer.resolve_named(name, str(root), origin="--profile" if profile else None, quiet=quiet)
    return res.name, eslint_rules(load_rules(res.data.get("architecture_rules")).rules)
