"""B4 split — empirical surface-parity guards for the dev_server package.

Added during campaign `2026-05-25-bloat-cleanup-B-shipwright` sub-iterate
B4 in response to external-review feedback. Both reviewers asked for
empirical assertions rather than relying on manually curated
`__init__.py` re-exports.

This file lives separately from `test_dev_server_multiservice.py`
because the multiservice suite is already at its grandfathered baseline
size — adding the parity guards there would ratchet that file's
`current` upward, which the bloat anti-ratchet hook (and the
campaign's cleanup-invariant) explicitly forbid.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dev_server  # noqa: E402


def test_b4_split_public_surface_present():
    """Names callers / tests / monkeypatches expect on `dev_server` post-split.

    Enumerates every name addressed by the existing test suite +
    downstream callers + the legacy compat shim list. A regression
    here means a future submodule move dropped something on the floor.
    """
    expected = {
        # Public commands
        "cmd_start", "cmd_start_with_services", "cmd_stop", "cmd_status",
        "main", "main_with_args",
        # Constants
        "STATE_FILE", "STATE_VERSION", "LOOPBACK_HOSTS", "PROFILE_DEV_SERVERS",
        # Module aliases monkeypatched by tests
        "os", "subprocess",
        # Lazy resolver (B3 lesson)
        "resolve_executable",
        # Internal helpers tests address by name
        "_DEFAULT_SERVICE", "_PLACEHOLDER_RE", "_StartFailed",
        "_already_running_owned", "_clear_state", "_emit_warnings",
        "_expand_env", "_get_config", "_get_services",
        "_get_services_for_test", "_http_probe", "_is_pid_running",
        "_is_port_in_use", "_is_port_in_use_for_host", "_kill_one",
        "_load_profile_data", "_load_state", "_normalize_legacy_dev_server",
        "_normalize_service_entry", "_pick_primary", "_probe_hosts_for",
        "_profiles_dir", "_rollback_and_report", "_save_state",
        "_save_state_atomic", "_service_url", "_services_from_profile_data",
        "_start_one", "_topo_sort", "_validate_services", "_wait_for_ready",
        "_wait_for_service",
    }
    missing = sorted(n for n in expected if not hasattr(dev_server, n))
    assert missing == [], f"Missing post-split exports on `dev_server`: {missing}"


def test_b4_split_import_resolves_to_package_not_shim():
    """Empirical proof that `import dev_server` resolves to the new package.

    Reviewer Gemini flagged the file/package name collision as the
    single biggest risk. The empirical contract is: with both
    `shared/scripts/dev_server.py` (shim) and `shared/scripts/dev_server/`
    (package) present, Python's import system MUST resolve `import
    dev_server` to the package. If a future change ever inverts this
    (e.g. via metapath finder reordering), this test fails loudly.
    """
    import os as _os

    pkg_file = _os.path.normpath(dev_server.__file__)
    # Package's __file__ is its __init__.py — not the sibling shim.
    assert pkg_file.endswith(_os.path.join("dev_server", "__init__.py")), (
        f"`import dev_server` did NOT resolve to the package; got "
        f"__file__={pkg_file!r}. The package directory must take "
        f"precedence over the sibling dev_server.py shim."
    )
