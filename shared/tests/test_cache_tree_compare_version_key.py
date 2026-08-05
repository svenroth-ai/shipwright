"""Direct unit pin for ``cache_tree_compare.version_key`` and its one consumer.

No test imported this module's ``version_key``/``latest_cache_version_dir``
directly before this file — coverage came only sideways, through
``check_plugin_cache_sync.py``'s fallback path
(``test_plugin_cache_version_resolution.py::TestFallbackIsHonest``) and
through the vendored hook's OWN copy
(``test_ensure_shared_cache_walk.py::test_version_key_orders_numerically_not_lexically``).
Neither exercised a SemVer prerelease suffix.

trg-18da39b0: a pure lexical tail comparison makes ``1.0.0-rc1`` sort AFTER
``1.0.0`` — ``'-rc1' > ''`` as a string — so a prerelease would be picked as
the newest installed version. SemVer says the opposite: a release outranks
every prerelease of the same numeric version.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    # APPEND, matching every sibling cache module: prepending would let
    # scripts/'s top-level names win resolution for the whole pytest process
    # (ADR-045 lib-collision, one directory over).
    sys.path.append(str(_SCRIPTS))

from cache_tree_compare import latest_cache_version_dir, version_key  # noqa: E402


def test_orders_numerically_not_lexically():
    """``0.10.0`` is NEWER than ``0.2.0`` — lexically it sorts the other way."""
    assert version_key("0.10.0") > version_key("0.2.0")
    assert version_key("1.0.0") > version_key("0.29.1")
    assert version_key("not-a-version") < version_key("0.0.1")


def test_a_release_outranks_every_prerelease_of_the_same_version():
    """SemVer: ``1.0.0`` outranks ``1.0.0-rc1`` — the release, not the tag.

    Before the fix the suffix compared as a raw string tail: any non-empty
    tail sorts above ``''``, so the prerelease won. Two different prereleases
    of the same numeric version must both still lose to the release.
    """
    assert version_key("1.0.0") > version_key("1.0.0-rc1")
    assert version_key("1.0.0") > version_key("1.0.0-beta")
    assert version_key("0.2.0") > version_key("0.2.0-rc1")


def test_prerelease_ordering_does_not_leak_across_numeric_versions():
    """A flag that ranks releases above prereleases must not override the
    numeric triplet — a newer prerelease still beats an older release."""
    assert version_key("1.1.0-rc1") > version_key("1.0.0")
    assert version_key("2.0.0-alpha") > version_key("1.9.9")


def test_latest_cache_version_dir_picks_the_release_over_a_prerelease(tmp_path: Path):
    """The one real consumer: must not report a prerelease as the cache's
    current version when a release of the same numeric version is present."""
    plugin_cache = tmp_path / "shipwright-foo"
    for version in ("1.0.0-rc1", "1.0.0", "0.9.0"):
        (plugin_cache / version).mkdir(parents=True)

    chosen, reason = latest_cache_version_dir(plugin_cache)

    assert reason == ""
    assert chosen.name == "1.0.0", f"picked {chosen.name}, not the release"
