"""Drift pins for the values the self-heal hook is forced to DUPLICATE.

``ensure_shared_cache`` is stdlib-only — it repairs the very ``shared/`` it would
otherwise import from — so it cannot reuse `scripts/cache_tree_compare`. Two
values are therefore second copies, and the Registry-driven-SSoT rule says a
duplicated value needs a test asserting the equivalence it claims:

- ``_IGNORE_NAMES`` vs the trees' PRODUCER and CHECKER;
- ``_version_key`` vs ``cache_tree_compare.version_key``.

**The producer pin is the one with teeth.** Pinning only against the *checker*
(`SKIP_DIRS`) misses names that `scripts/update-marketplace.sh` — the tool that
actually writes these trees — withholds. Such a name can never appear in the
destination, so the tree is permanently "incomplete" and the hook re-copies it on
every session start forever. `.python-version` is exactly that case, and it was
invisible to a live-cache probe because no install had delivered one yet.

Companions: ``…_walk`` (walk semantics), ``…_partial_reap`` (surviving-sentinel
behaviour), ``…_integration`` (fresh-install delivery), ``…_vendored`` (the
13-copy byte-identity gate).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
_SCRIPTS = _REPO / "scripts"
for _p in (_HERE, _SCRIPTS):
    if str(_p) not in sys.path:
        # APPEND, never insert(0) — prepending would let scripts/'s top-level
        # module names win resolution for the whole pytest process (ADR-045).
        sys.path.append(str(_p))

from cache_tree_compare import ORPHAN_MARKER, SKIP_DIRS, SKIP_SUFFIXES, version_key  # noqa: E402
from ensure_shared_cache_fixtures import CANONICAL, hook_module  # noqa: E402

_HOOK = hook_module()


def test_ignore_set_covers_every_cache_tree_compare_skip_dir():
    missing = SKIP_DIRS - set(_HOOK._IGNORE_NAMES)
    assert not missing, (
        f"the self-heal hook ignores fewer paths than the drift gate: {sorted(missing)}. "
        "A name the gate skips and the hook counts is a permanent phantom gap that "
        "re-copies the cache every session."
    )


def test_ignore_set_covers_the_cache_tree_compare_skip_suffixes():
    """`*.pyc` / `*.pyo` are patterns in the hook, bare suffixes in the checker."""
    patterns = set(_HOOK._IGNORE_NAMES)
    missing = [s for s in SKIP_SUFFIXES if f"*{s}" not in patterns and s not in patterns]
    assert not missing, f"hook does not ignore {missing} (cache_tree_compare.SKIP_SUFFIXES)"


def test_ignore_set_covers_the_orphan_marker():
    assert ORPHAN_MARKER in set(_HOOK._IGNORE_NAMES)


def test_ignore_set_covers_every_name_the_PRODUCER_withholds():
    """Parity with the tool that WRITES the trees, not merely the one that checks.

    Measured instance: all 14 plugins carry a tracked `.python-version` which
    `update-marketplace.sh` drops at all three sync sites on purpose
    (iterate-2026-08-01-pin-python-311). Absent from the live cache when this
    change was probed, so only reading the producer catches it.
    """
    script = (_REPO / "scripts" / "update-marketplace.sh").read_text(encoding="utf-8")
    withheld = set(re.findall(r'-not\s+-name\s+"([^"]+)"', script))
    assert withheld, "parsed no exclusions — the `-not -name` convention changed"

    names = set(_HOOK._IGNORE_NAMES)
    missing = sorted(w for w in withheld if w not in names)
    assert not missing, (
        f"update-marketplace.sh withholds {missing} from the cache, but the self-heal "
        "hook counts them as deliverable. Each is a permanent phantom gap: the mirror "
        "can never satisfy the completeness check, so every session start re-copies "
        "the whole tree. Add them to _IGNORE_NAMES."
    )


def test_version_key_is_equivalent_to_the_shared_implementation():
    """The duplication is justified (stdlib-only); the EQUIVALENCE needs the pin."""
    for name in ("0.10.0", "0.2.0", "0.2.1", "1.0.0", "0.29.1", "0.3.1",
                 "0.2.0-rc1", "10.0.0", "not-a-version", "0.2", ""):
        assert _HOOK._version_key(name) == version_key(name), (
            f"_version_key diverged from cache_tree_compare.version_key on {name!r}"
        )


def test_every_copy_site_passes_the_shared_ignore_callable():
    """The walk and the copies must share ONE ignore callable.

    If a `copytree` dropped `ignore=_IGNORE`, it would deliver files the walk
    excludes and omit none — but a hand-rolled second list in either direction
    re-opens the permanent-gap failure this whole design is built to avoid.
    """
    source = CANONICAL.read_text(encoding="utf-8")
    # real call sites only — `shutil.copytree(`; bare `copytree(` also appears in
    # prose, and a docstring is not something this pin should be able to satisfy.
    copy_sites = re.findall(r"shutil\.copytree\(([^)]*)\)", source)
    assert len(copy_sites) >= 2, f"expected the shared/ and plugins/ copies, got {copy_sites}"
    for site in copy_sites:
        assert "ignore=_IGNORE" in site, (
            f"a copytree call does not pass ignore=_IGNORE: {site!r}"
        )
