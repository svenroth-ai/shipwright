"""The inline-suppression baseline file: schema, validation, seeding.

Third leaf of the trio (``inline_suppression_scan`` discovers,
``inline_suppressions`` applies the rule, this one owns the FILE). Split out
when the rule module crossed the 300-line cap, along the seam the register
already uses — ``accepted_risks`` owns its register document the same way.

**Validation is unforgiving on purpose.** A baseline entry licenses a real
security finding to stay silenced, so a half-filled row is an ERROR, never a
skipped one: a skipped row reads as "nothing licensed" while the suppression
stays live, which is precisely the state this file exists to make impossible.

**Absent is not exempt.** An absent baseline reads as empty — meaning every
discovered rule comes back UNRECORDED, not waved through. Deleting the file
must not silence the gate (the lesson of
iterate-2026-07-31-accepted-risk-gate-holes, learned there by the register).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from accepted_risks import DECISION_REF_RE
from inline_suppression_scan import scan_sites

#: Repo-root baseline. Follows the ``shipwright_`` config-file prefix.
BASELINE_NAME = "shipwright_inline_suppressions.json"
SCHEMA_VERSION = 1

_ALLOWED_KEYS = frozenset({"rule", "max_sites", "rationale_ref", "statement"})
#: ``_readme`` is load-bearing: the file is hand-edited and JSON has no
#: comments, so the operating instructions have to live inside the document.
_ALLOWED_TOP_KEYS = frozenset({"schema", "rules", "_readme"})
#: Matches the register's own ``_MIN_STATEMENT_CHARS`` — same discipline, same
#: reason: a half-filled row reads as governance while suppressing for real.
_MIN_STATEMENT_CHARS = 20


class BaselineError(ValueError):
    """The baseline exists but cannot be trusted — always fail closed."""


def baseline_path(project_root: Path | str) -> Path:
    return Path(project_root) / BASELINE_NAME


def _entry_error(entry: Any, index: int, seen: set[str]) -> str | None:
    """The single validation violation for one entry, or ``None`` if clean."""
    where = f"rules[{index}]"
    if not isinstance(entry, dict):
        return f"{where}: must be a mapping, got {type(entry).__name__}"

    unknown = sorted(set(entry) - _ALLOWED_KEYS)
    if unknown:
        return f"{where}: unknown key(s) {', '.join(unknown)}"

    rule = entry.get("rule")
    if not isinstance(rule, str) or not rule.strip():
        return f"{where}: missing or empty 'rule' (the semgrep rule id)"
    where = f"rules[{index}] ({rule})"
    if rule in seen:
        return f"{where}: duplicate rule — one rule, one entry"

    count = entry.get("max_sites")
    # `bool` is an `int` subclass, so `true` would otherwise pass as 1
    # (external review, GPT #3). Zero is rejected separately below rather than
    # lumped in, because the two are different mistakes with different fixes.
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return f"{where}: 'max_sites' must be a non-negative integer"
    if count == 0:
        # A zero entry is DEAD the moment it is written and can never be
        # satisfied: the rule is suppressed nowhere, so `reconcile` blocks and
        # tells the operator to delete it. Accepting a value the rule makes
        # permanently unsatisfiable is a schema that contradicts its own gate
        # (Stage-3 doubt review, D7). There is deliberately no way to express
        # "this rule may never be suppressed" — absence already says that, and
        # says it without a record to maintain.
        return (
            f"{where}: 'max_sites' of 0 is not a way to forbid a rule — an "
            "entry licensing nothing is dead on arrival and blocks forever. "
            "Delete the entry instead; a rule with no entry already blocks."
        )

    ref = entry.get("rationale_ref")
    if not isinstance(ref, str) or not DECISION_REF_RE.search(ref):
        return (
            f"{where}: 'rationale_ref' must NAME a recorded decision "
            f"(ADR-NNN, an iterate-YYYY-MM-DD-slug run id, or #NNN) — got {ref!r}"
        )

    statement = entry.get("statement")
    if not isinstance(statement, str) or len(
            statement.strip()) < _MIN_STATEMENT_CHARS:
        return (
            f"{where}: 'statement' must say why this rule is suppressed inline, "
            f"in at least {_MIN_STATEMENT_CHARS} characters"
        )
    return None


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    """``json.loads`` silently keeps the LAST of two identical keys, so a
    hand-edited baseline could carry a shadowed ``max_sites`` that no reader
    reports (external review, GPT #3)."""
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise BaselineError(f"{BASELINE_NAME}: duplicate JSON key {key!r}")
        out[key] = value
    return out


def load_baseline(project_root: Path | str) -> dict[str, dict]:
    """``{rule_id: entry}``. Absent → ``{}``; present-but-invalid → raise.

    Validation is all-or-nothing, so a partially-parsed baseline can never be
    mistaken for a complete one.
    """
    path = baseline_path(project_root)
    if not path.is_file():
        return {}
    try:
        doc = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_no_duplicate_keys,
        )
    except OSError as exc:
        raise BaselineError(f"{BASELINE_NAME} is unreadable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BaselineError(f"{BASELINE_NAME} is not valid JSON: {exc}") from exc

    if not isinstance(doc, dict):
        raise BaselineError(f"{BASELINE_NAME} must be a JSON object")
    # Symmetric with the per-entry check. Without it a governance-looking
    # top-level key (`expires`, say) would sit in the file reading as though it
    # constrained something, while nothing ever read it (Stage-2 code review).
    unknown_top = sorted(set(doc) - _ALLOWED_TOP_KEYS)
    if unknown_top:
        raise BaselineError(
            f"{BASELINE_NAME}: unknown top-level key(s) "
            f"{', '.join(unknown_top)} — nothing reads them, so they would "
            "look like governance while constraining nothing"
        )
    if doc.get("schema") != SCHEMA_VERSION:
        raise BaselineError(
            f"{BASELINE_NAME}: unsupported schema {doc.get('schema')!r} "
            f"(this reader understands {SCHEMA_VERSION})"
        )
    if not isinstance(doc.get("rules"), list):
        raise BaselineError(f"{BASELINE_NAME}: 'rules' must be a list")

    out: dict[str, dict] = {}
    for index, entry in enumerate(doc["rules"]):
        problem = _entry_error(entry, index, set(out))
        if problem:
            raise BaselineError(problem)
        out[entry["rule"]] = dict(entry)
    return out


def dump_baseline(entries: dict[str, dict]) -> dict:
    """The on-disk document for ``entries`` — the inverse of `load_baseline`."""
    return {
        "schema": SCHEMA_VERSION,
        "rules": [entries[r] for r in sorted(entries)],
    }


def seed_baseline(
    project_root: Path | str, *, rationale_ref: str, statement: str
) -> dict:
    """A baseline document pinning this tree's CURRENT counts exactly.

    No headroom: a ratchet whose baseline starts loose permits the first
    regression for free.
    """
    return dump_baseline({
        rule: {
            "rule": rule,
            "max_sites": len(sites),
            "rationale_ref": rationale_ref,
            "statement": statement,
        }
        for rule, sites in scan_sites(project_root).items()
    })
