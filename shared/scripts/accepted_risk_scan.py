"""Discover the suppressions that are actually in effect, from version control.

Leaf module, deliberately: both the reconciler CLI and the compliance dashboard
need this, and a shared LEAF that each imports by its unique top-level name is
the pattern that keeps them in lockstep without either importing the other's
package (ADR-044/045 — mirrors ``gh_action_tag_owner``, which the security
plugin and the shared ingest path both consume this way).

"In effect" here is scoped to the channels the register's ``target`` vocabulary
can be reconciled against: the Trivy ignore file and the ``SHIPWRIGHT_SEMGREP_*``
env vars in ``security.yml``. It does NOT mean *source-controlled* generally —
an inline ``# nosemgrep`` is source-controlled and in effect, and no ``target``
covers it, so reading the two as equivalent is what makes an inline suppression
look like it needs a register entry. A GitHub code-scanning dismissal is live
API state, not a file, so it is outside this module's reach for the opposite
reason — see ``accepted_risks.STATIC_TARGETS``.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from accepted_risks import (
    TARGET_SEMGREP_RULE,
    TARGET_SEMGREP_TOGGLE,
    TARGET_TRIVY_IGNORE,
    coerce_date,
    today_utc,
)
from gh_action_tag_owner import (
    ACCEPT_GH_ACTION_TAGS_ENV,
    accept_github_owned_action_tags,
)

#: Both YAML spellings Trivy accepts, plus the classic flat-text form. The
#: compliance parser used to read only the two YAML names while the SCANNER
#: (``oss_backend._resolve_trivy_ignorefile``) also honoured the flat file — so a
#: repo using it got real suppression with zero dashboard visibility.
TRIVYIGNORE_YAML_NAMES = (".trivyignore.yaml", ".trivyignore.yml")
TRIVYIGNORE_FLAT_NAME = ".trivyignore"

SECURITY_WORKFLOW_REL = Path(".github/workflows/security.yml")

#: Env var carrying the wholesale rule-exclusion list (comma-separated).
EXCLUDE_RULES_ENV = "SHIPWRIGHT_SEMGREP_EXCLUDE_RULES"

#: Trivy's per-entry expiry field in the classic flat form: ``CVE-1 exp:2026-01-01``.
#: The YAML form spells the same thing ``expired_at:``.
FLAT_EXPIRY_FIELD = "exp:"

#: Targeted extraction of `KEY: value` env lines. ``yaml.safe_load`` is NOT used
#: on a GitHub Actions workflow: an unquoted ``if: ${{ ... }}`` opens a YAML flow
#: mapping and breaks strict parsers (external review, Gemini).
_ENV_LINE_RE = re.compile(r"^\s*(SHIPWRIGHT_[A-Z0-9_]+)\s*:\s*(.*?)\s*$")


def _unquote(value: str) -> str:
    """Strip surrounding quotes and any trailing YAML comment."""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    # In YAML a `#` only starts a comment when preceded by whitespace.
    return text.split(" #", 1)[0].strip()


def read_workflow_env(project_root: Path | str) -> dict[str, str]:
    """The ``SHIPWRIGHT_*`` env assignments in ``security.yml`` (read-only).

    Commented-out lines are skipped, so the prose block that documents each
    channel directly above the real assignment never counts as a suppression.
    """
    path = Path(project_root) / SECURITY_WORKFLOW_REL
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        match = _ENV_LINE_RE.match(line)
        if match:
            out[match.group(1)] = _unquote(match.group(2))
    return out


def _is_lapsed(raw_expiry: Any, now: date) -> bool:
    """True once Trivy has STOPPED applying an entry with this due date.

    Mirrors Trivy's own rule rather than its prose (``pkg/result/ignore.go``)::

        !finding.ExpiredAt.IsZero() && finding.ExpiredAt.Before(clock.Now(ctx))

    ``ExpiredAt`` parses with layout ``2006-01-02`` — midnight — so any real
    ``now`` on the date itself is already past it. In date terms an entry lapses
    **from** its ``expired_at``, which is deliberately one day earlier than
    :meth:`accepted_risks.Acceptance.is_expired`. The two are NOT the same
    question and must not be unified: that one asks when the register's own
    re-review falls due, this one asks what the scanner is doing today.

    No date — or one that does not parse — means "no expiry" and keeps the entry
    active. That is the fail-safe direction: an entry counted as active merely
    has to be recorded, whereas one wrongly counted as absent would report a
    live suppression as STALE and send the operator to delete a register entry
    that is doing its job.

    Two disclosed limits of the mirror:

    * **Clock.** Trivy's ``clock.Now(ctx)`` is local time; this resolves
      ``today_utc()``. So on a non-UTC runner the two can disagree for at most
      one day. Deliberate — ``today_utc``'s own docstring gives the reason: the
      register must not flip expired/active between a CI runner and a laptop.
    * **Unparseable dates are over-counted in the YAML form.** Trivy unmarshals
      ``expired_at`` into a ``time.Time``, so ``expired_at: whenever`` makes it
      reject the WHOLE ignore file and suppress nothing; keeping the entry
      active is permissive there. The flat form genuinely tolerates a malformed
      ``exp:``. Not corrected here — the failure contract for a structurally
      invalid ignore file is out of scope for
      iterate-2026-07-31-accepted-risk-gate-holes and filed on its own.
    """
    if raw_expiry is None:
        return False
    parsed = coerce_date(raw_expiry)
    return parsed is not None and parsed <= now


def _flat_id(raw_line: str, now: date) -> str | None:
    """The still-active id on one classic ``.trivyignore`` line, if any.

    Trivy's flat form is whitespace-separated fields with ``#`` comments, the
    optional ``exp:YYYY-MM-DD`` field carrying the entry's own expiry::

        CVE-2019-14697 exp:2023-01-01

    The comment is stripped BEFORE splitting, so a blank, whitespace-only or
    comment-only line yields nothing instead of becoming a discovered
    suppression. The id is the first non-``exp:`` field — previously the whole
    line was taken verbatim, so an entry carrying an expiry could never match a
    register ``rule`` at all.
    """
    fields = raw_line.split("#", 1)[0].split()
    if not fields:
        return None
    expiry = next(
        (f[len(FLAT_EXPIRY_FIELD):] for f in fields
         if f.startswith(FLAT_EXPIRY_FIELD)),
        None,
    )
    if _is_lapsed(expiry, now):
        return None
    return next((f for f in fields if not f.startswith(FLAT_EXPIRY_FIELD)), None)


def read_trivyignore_ids(
    project_root: Path | str, *, now: date | None = None
) -> set[str]:
    """Suppressed ids from whichever ``.trivyignore`` form the repo uses.

    An entry whose OWN due date has lapsed is omitted, because Trivy has stopped
    applying it: counting it would let the gate report the register "reconciled"
    against a suppression that is no longer in effect, which is precisely the
    state that renewing only the register's date produces
    (iterate-2026-07-31-accepted-risk-gate-holes).
    """
    now = now or today_utc()
    root = Path(project_root)
    for name in TRIVYIGNORE_YAML_NAMES:
        path = root / name
        if path.is_file():
            import yaml  # noqa: PLC0415

            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                return set()
            if not isinstance(doc, dict):
                return set()
            return {
                str(e["id"])
                for e in (doc.get("vulnerabilities") or [])
                if isinstance(e, dict) and e.get("id")
                and not _is_lapsed(e.get("expired_at"), now)
            }
    flat = root / TRIVYIGNORE_FLAT_NAME
    if flat.is_file():
        # Classic form: one id per line with `#` comments — NOT YAML.
        try:
            lines = flat.read_text(encoding="utf-8").splitlines()
        except OSError:
            return set()
        return {
            found for raw in lines if (found := _flat_id(raw, now)) is not None
        }
    return set()


def discovered_suppressions(
    project_root: Path | str, *, now: date | None = None
) -> dict[str, set[str]]:
    """The three reconcilable ``target`` channels, keyed by target.

    Exactly the Trivy ignore ids, ``SHIPWRIGHT_SEMGREP_EXCLUDE_RULES`` and the
    semgrep policy toggle — not every suppression in effect, and not even every
    one in this env block: ``SHIPWRIGHT_SCAN_EXCLUDES`` scopes *paths* rather
    than rules and has no ``target``, as does an inline ``# nosemgrep``. An
    entry registered for either matches no discovered suppression, which is the
    *stale* half of the both-directions gate and fails the build.

    ``now`` is resolved ONCE here and passed down, so a caller that supplies its
    own date (the compliance dashboard does) gets an answer derived entirely
    from it and one straddling midnight cannot answer two different ways within
    a single operation. Only the Trivy channel carries per-entry expiry; the
    semgrep env vars have none and are never filtered by it.
    """
    now = now or today_utc()
    env = read_workflow_env(project_root)
    # Comma-separated — mirrors semgrep_tailoring._resolve_exclude_rule_ids.
    exclude_rules = {
        r.strip() for r in env.get(EXCLUDE_RULES_ENV, "").split(",") if r.strip()
    }

    toggles: set[str] = set()
    # Reuse the producer's own truthiness rather than re-deriving "1" == on.
    if accept_github_owned_action_tags(env):
        toggles.add(ACCEPT_GH_ACTION_TAGS_ENV)

    return {
        TARGET_TRIVY_IGNORE: read_trivyignore_ids(project_root, now=now),
        TARGET_SEMGREP_RULE: exclude_rules,
        TARGET_SEMGREP_TOGGLE: toggles,
    }
