"""Drift test pinning the gitleaks-config template to the convention lock.

The deployed ``security.yml`` runs ``gitleaks detect --no-git`` with **no**
``--config``, so gitleaks auto-loads ``.gitleaks.toml`` from the repo root when
present. /shipwright-adopt scaffolds that file (via
``gitleaks_config_scaffolder``) from the template at
``GITLEAKS_CONFIG_TEMPLATE_PATH``; without it every adopted repo's first scan
goes RED on the built-in ``sidekiq-secret`` rule false-matching the magic-hex
placeholder ``cafebabe:deadbeef`` (proven on leadwright 2026-06-07: run
27086046885 red -> 27086178138 green after the file was added).

The convention lock at ``shared/scripts/lib/security_workflow.py`` is the single
source of truth for the companion template path + the deployed-file path. This
test is the forward half of the registry-driven SSoT rule: every path constant
must resolve to a real file with the required shape. Without it the constant
could declare a template that doesn't exist (adopt scaffolds an empty file) or a
template whose allowlist silently lost the placeholder suppression (the
red-first-run gap reopens) or — worse — dropped ``useDefault`` and disabled
real secret detection.
"""

from __future__ import annotations

from pathlib import Path

from lib.security_workflow import (
    GITLEAKS_CONFIG_PATH,
    GITLEAKS_CONFIG_TEMPLATE_PATH,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GITLEAKS_TEMPLATE_FILE = REPO_ROOT / GITLEAKS_CONFIG_TEMPLATE_PATH


def _template_text() -> str:
    assert GITLEAKS_TEMPLATE_FILE.exists(), (
        f"gitleaks config template missing at {GITLEAKS_TEMPLATE_FILE}.\n"
        f"  Convention lock (shared/scripts/lib/security_workflow.py) declares "
        f"GITLEAKS_CONFIG_TEMPLATE_PATH={GITLEAKS_CONFIG_TEMPLATE_PATH!r} but the "
        f"file is absent.\n  Either author the template or update the constant."
    )
    return GITLEAKS_TEMPLATE_FILE.read_text(encoding="utf-8")


class TestGitleaksConfigPathConstant:
    """The deployed ``.gitleaks.toml`` must sit at the repo root so a
    ``gitleaks detect --no-git`` (no ``--config``) auto-loads it."""

    def test_gitleaks_config_path_is_root_toml(self):
        assert GITLEAKS_CONFIG_PATH == ".gitleaks.toml", (
            f"GITLEAKS_CONFIG_PATH={GITLEAKS_CONFIG_PATH!r} — gitleaks only "
            f"auto-loads a config named `.gitleaks.toml` from the scan root."
        )


class TestGitleaksConfigTemplate:
    """The template must extend the default ruleset and allowlist ONLY the
    self-evident magic-hex placeholder — never a blanket secret suppression."""

    def test_extends_default_ruleset(self):
        text = _template_text()
        assert "useDefault = true" in text, (
            "gitleaks template must `[extend] useDefault = true` — dropping the "
            "built-in ruleset would silently disable real secret detection."
        )

    def test_allowlists_magic_hex_placeholder(self):
        text = _template_text()
        assert "cafebabe:deadbeef" in text, (
            "the cafebabe:deadbeef placeholder is the one false positive this "
            "config exists to suppress — its absence reopens the red-first-run gap."
        )
        assert 'regexTarget = "match"' in text, (
            "allowlist must target the matched `match` text, mirroring "
            "shipwright-webui/.gitleaks.toml."
        )

    def test_has_magic_hex_stopwords(self):
        # Belt-and-suspenders: any finding containing these famous magic-hex
        # constants is treated as a non-secret regardless of rule.
        text = _template_text()
        assert '"cafebabe"' in text
        assert '"deadbeef"' in text
