"""Regression: update-marketplace.sh brings EVERY registered plugin into the cache.

The sync used to refresh only already-installed plugins and silently skip a
registered-but-not-installed one, leaving the opt-in shipwright-grade lead magnet
permanently ``not_in_cache``. It must now install a missing registered plugin
from the marketplace instead of skipping it.

Split out of ``test_installer_shell_scripts.py`` (a bloat-baselined module) so
the new coverage does not ratchet that file — the F37 shell-lint assertions there
still cover the whole script text.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "update-marketplace.sh"


def _read() -> str:
    return UPDATE_SH.read_text(encoding="utf-8")


def test_installs_missing_registered_plugin_instead_of_skipping():
    src = _read()
    assert re.search(r'claude plugin install\s+"\$plugin_key"', src), (
        "update-marketplace.sh no longer installs a not-yet-installed registered "
        "plugin — it will silently skip it and leave it not_in_cache"
    )


def test_install_is_guarded_by_the_shared_resolver():
    # A shared resolver drives the (guarded) install, so an already-installed
    # plugin is only re-queried, never re-installed.
    assert "_install_path" in _read(), "the shared install-path resolver helper is gone"


def test_new_helper_keeps_f37_no_bare_python():
    # F37 parity: the added helper must not reintroduce a bare `python -c` (aborts
    # under set -e where only python3 exists — Debian/Ubuntu/macOS).
    assert not re.findall(r"\$\(\s*python\s+-c", _read())
