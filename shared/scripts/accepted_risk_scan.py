"""Discover the suppressions that are actually in effect, from version control.

Leaf module, deliberately: both the reconciler CLI and the compliance dashboard
need this, and a shared LEAF that each imports by its unique top-level name is
the pattern that keeps them in lockstep without either importing the other's
package (ADR-044/045 — mirrors ``gh_action_tag_owner``, which the security
plugin and the shared ingest path both consume this way).

"In effect" here means *source-controlled*: the Trivy ignore file and the
``SHIPWRIGHT_SEMGREP_*`` env vars in ``security.yml``. A GitHub code-scanning
dismissal is live API state, not a file, so it is deliberately outside this
module's reach — see ``accepted_risks.STATIC_TARGETS``.
"""

from __future__ import annotations

import re
from pathlib import Path

from accepted_risks import (
    TARGET_SEMGREP_RULE,
    TARGET_SEMGREP_TOGGLE,
    TARGET_TRIVY_IGNORE,
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


def read_trivyignore_ids(project_root: Path | str) -> set[str]:
    """Suppressed ids from whichever ``.trivyignore`` form the repo uses."""
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
            }
    flat = root / TRIVYIGNORE_FLAT_NAME
    if flat.is_file():
        # Classic form: one id per line with `#` comments — NOT YAML.
        try:
            lines = flat.read_text(encoding="utf-8").splitlines()
        except OSError:
            return set()
        return {
            stripped
            for raw in lines
            if (stripped := raw.split("#", 1)[0].strip())
        }
    return set()


def discovered_suppressions(project_root: Path | str) -> dict[str, set[str]]:
    """Every source-controlled suppression currently in effect, keyed by target."""
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
        TARGET_TRIVY_IGNORE: read_trivyignore_ids(project_root),
        TARGET_SEMGREP_RULE: exclude_rules,
        TARGET_SEMGREP_TOGGLE: toggles,
    }
