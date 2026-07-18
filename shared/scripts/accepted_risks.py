"""Scanner-agnostic accepted-risk register — the single human-authored record.

Accepting a security finding used to mean doing one of three unrelated things,
only one of which a human ever saw again:

* ``.trivyignore.yaml`` — SCA only, but the **only** channel carrying a due date
  (``expired_at``), surfaced by the compliance dashboard as ``EXPIRED — re-review``;
* ``SHIPWRIGHT_SEMGREP_*`` env vars in ``security.yml`` — SAST rules, no expiry,
  rationale living in a prose table in ``docs/security-ci-setup.md``;
* a manual dismissal in the GitHub Security tab — no expiry, invisible from the repo.

Because the expiry was bolted to the Trivy channel, webui had to register a
**Semgrep / CI-posture** decision inside a **Trivy** ignore file just to obtain a
due date — an acknowledged semantic stretch, and the direct motivation for this
module (triage ``trg-15a8e267``, item 4 of ``trg-9509c2e8``).

``shipwright_accepted_risks.yaml`` records the acceptance; the scanner wiring is
deliberately left where it is. A both-directions drift gate
(``tools/accepted_risks_cli.py check``) ties the two together, which buys the
single-record property without turning a live security gate into a generated
artifact.

**Validation is unforgiving on purpose.** An acceptance silences a real security
signal, so a half-filled entry is an ERROR, never a skipped row — a skipped row
reads as "nothing accepted" while the suppression stays live, which is precisely
the state this register exists to make impossible.

**Absent is not malformed** (external review, GPT #8). An absent register is a
legacy or fresh repo and reads as empty; a present-but-malformed one fails
closed. Collapsing the two would let one broken edit read as "all entries
removed" and, downstream in ``alert_convergence``, license a mass-dismissal off
a truncated file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

#: Repo-root register filename. Follows the ``shipwright_`` config prefix
#: convention; YAML (not JSON) because it is hand-written and needs comments.
REGISTER_NAME = "shipwright_accepted_risks.yaml"
SCHEMA_VERSION = 1

TARGET_TRIVY_IGNORE = "trivy-ignore"
TARGET_SEMGREP_RULE = "semgrep-rule-exclusion"
TARGET_SEMGREP_TOGGLE = "semgrep-policy-toggle"
TARGET_GITHUB_DISMISSAL = "github-dismissal"

#: Every acceptance target the register understands.
TARGETS = (
    TARGET_TRIVY_IGNORE,
    TARGET_SEMGREP_RULE,
    TARGET_SEMGREP_TOGGLE,
    TARGET_GITHUB_DISMISSAL,
)

#: The subset whose operational counterpart lives in version control and can
#: therefore be reconciled **offline**. ``github-dismissal`` is deliberately
#: excluded: a CodeQL/Scorecard acceptance is a live GitHub alert state, not a
#: file, so an offline gate can only report that it did not check it (it must
#: never silently treat "not checkable here" as "checked and fine").
STATIC_TARGETS = (
    TARGET_TRIVY_IGNORE,
    TARGET_SEMGREP_RULE,
    TARGET_SEMGREP_TOGGLE,
)

#: ``rationale_ref`` must NAME a recorded decision — "N/A" / "TODO" / "we talked
#: about it" is exactly the filler this register exists to refuse. Duplicated
#: from ``tools/verifiers/ci_supplychain._DECISION_REF_RE`` on purpose: that
#: verifier must stay self-contained (ADR-044). ``test_accepted_risks``
#: pins the two equal, so neither can drift alone.
#: Literal alternation with bounded classes — linear, no nested quantifiers
#: (ReDoS-safe; unbounded repetition here is a CodeQL HIGH).
DECISION_REF_RE = re.compile(
    r"(ADR-\d+|iterate-\d{4}-\d{2}-\d{2}-[a-z0-9-]+|#\d+)", re.IGNORECASE
)

_MIN_STATEMENT_CHARS = 20


class RegisterError(ValueError):
    """The register exists but cannot be trusted — always fail closed."""


@dataclass(frozen=True)
class Acceptance:
    """One recorded, scoped, time-bounded risk acceptance."""

    id: str
    target: str
    rule: str
    expires: date
    rationale_ref: str
    statement: str
    scope: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: date) -> bool:
        """Expired only once the due date has *passed* — the date itself is
        still an active acceptance (matches the pre-existing ``expired_at``
        semantics in ``ci_security.parse_accepted_risks``)."""
        return self.expires < now

    @property
    def statically_checkable(self) -> bool:
        return self.target in STATIC_TARGETS


def today_utc() -> date:
    """Today in UTC.

    Expiry must not depend on the machine's timezone, or an entry flips
    expired/active across a CI runner and a laptop on the boundary day.
    """
    return datetime.now(timezone.utc).date()


def register_path(project_root: Path | str) -> Path:
    return Path(project_root) / REGISTER_NAME


def register_exists(project_root: Path | str) -> bool:
    return register_path(project_root).is_file()


def _coerce_date(value: Any) -> date | None:
    """A ``date`` from a YAML date or an ISO ``YYYY-MM-DD`` string.

    ``datetime`` is checked first because it is a *subclass* of ``date``.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _entry_error(entry: Any, index: int, seen: set[str]) -> str | None:
    """The single validation violation for one entry, or ``None`` if clean."""
    where = f"acceptances[{index}]"
    if not isinstance(entry, dict):
        return f"{where}: must be a mapping, got {type(entry).__name__}"

    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id.strip():
        return f"{where}: missing or empty 'id'"
    where = f"acceptances[{index}] ({entry_id})"
    if entry_id in seen:
        return f"{where}: duplicate id — one acceptance, one record"

    target = entry.get("target")
    if target not in TARGETS:
        return (
            f"{where}: unknown target {target!r} — must be one of "
            + ", ".join(TARGETS)
        )

    rule = entry.get("rule")
    if not isinstance(rule, str) or not rule.strip():
        return f"{where}: missing or empty 'rule' (the scanner-native id)"

    if _coerce_date(entry.get("expires")) is None:
        return (
            f"{where}: 'expires' missing or not a YYYY-MM-DD date "
            "— an acceptance without a due date is a blanket suppression"
        )

    ref = entry.get("rationale_ref")
    if not isinstance(ref, str) or not DECISION_REF_RE.search(ref):
        return (
            f"{where}: 'rationale_ref' must NAME a recorded decision "
            "(ADR-NNN, an iterate-YYYY-MM-DD-slug run id, #NNN, or DO-NOT #NNN) "
            f"— got {ref!r}"
        )

    statement = entry.get("statement")
    if not isinstance(statement, str) or len(statement.strip()) < _MIN_STATEMENT_CHARS:
        return (
            f"{where}: 'statement' must justify the acceptance in at least "
            f"{_MIN_STATEMENT_CHARS} characters"
        )

    scope = entry.get("scope", {})
    if scope is not None and not isinstance(scope, dict):
        return f"{where}: 'scope' must be a mapping when present"

    return None


def _parse_document(path: Path) -> dict:
    """Load and structurally validate the register document."""
    # Lazy import: PyYAML is not a dependency of every plugin that can reach
    # this module through a cross-plugin chain (mirrors ci_security, ADR-045).
    import yaml  # noqa: PLC0415

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegisterError(f"{REGISTER_NAME} is unreadable: {exc}") from exc
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RegisterError(f"{REGISTER_NAME} is not valid YAML: {exc}") from exc

    if doc is None:
        raise RegisterError(
            f"{REGISTER_NAME} is present but empty. If you meant to remove every "
            "acceptance, write an explicit `acceptances: []` — a truncated file "
            "must never read as 'nothing was ever accepted'."
        )
    if not isinstance(doc, dict):
        raise RegisterError(f"{REGISTER_NAME} must be a YAML mapping")
    if doc.get("schema") != SCHEMA_VERSION:
        raise RegisterError(
            f"{REGISTER_NAME}: unsupported schema {doc.get('schema')!r} "
            f"(this reader understands {SCHEMA_VERSION})"
        )
    if "acceptances" not in doc:
        raise RegisterError(f"{REGISTER_NAME}: missing required key 'acceptances'")
    if not isinstance(doc["acceptances"], list):
        raise RegisterError(f"{REGISTER_NAME}: 'acceptances' must be a list")
    return doc


def load_register(project_root: Path | str) -> list[Acceptance]:
    """Every acceptance in the register.

    Absent register → ``[]`` (legacy/fresh repo). Present-but-invalid →
    :class:`RegisterError`. Validation is all-or-nothing: a single bad entry
    fails the whole load, so a partially-parsed register can never be mistaken
    for a complete one.
    """
    path = register_path(project_root)
    if not path.is_file():
        return []

    doc = _parse_document(path)
    seen: set[str] = set()
    out: list[Acceptance] = []
    for index, entry in enumerate(doc["acceptances"]):
        problem = _entry_error(entry, index, seen)
        if problem:
            raise RegisterError(problem)
        seen.add(entry["id"])
        out.append(
            Acceptance(
                id=entry["id"],
                target=entry["target"],
                rule=entry["rule"],
                expires=_coerce_date(entry["expires"]),  # validated above
                rationale_ref=entry["rationale_ref"],
                statement=entry["statement"].strip(),
                scope=dict(entry.get("scope") or {}),
            )
        )
    return out


def expired(acceptances: list[Acceptance], now: date) -> list[Acceptance]:
    """The acceptances whose re-review date has passed."""
    return [a for a in acceptances if a.is_expired(now)]
