"""Drift protection for the false-verdict probe dispatch table.

``_probe_runner`` used to resolve a probe with ``globals()[f"probe_{name}"]``.
That lookup was self-consistent by construction -- the name in the CLI and the
name of the function were the same string, so they could not disagree -- but it
indexed the entire module namespace with a runtime-built key, which is
indistinguishable from arbitrary dispatch to a reader or a scanner.

Replacing it with an explicit ``name -> function`` table removes the dynamic
lookup and makes the mapping reviewable, at the cost of the property the old
form got for free: an explicit table CAN be wrong. ``"t1": probe_t2`` is valid
Python that silently runs the wrong check, and a probe with no row silently
stops being reachable. These tests are what buys that property back.

Split out of ``test_requirements_corpus_registry`` (which pins the TARGET
registry and baseline portability) so neither module carries an unrelated
second subject.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from requirements_corpus import _probe_runner  # noqa: E402

EXPECTED_PROBE_NAMES = {
    "t1", "t2", "group_d_empty", "group_i_empty",
    "d_traceability_empty", "d_traceability_populated",
    "unsorted_seam", "unsorted_seam_a2",
}


def test_the_probe_cli_offers_exactly_the_documented_names():
    """The CLI contract, pinned independently of the implementation.

    ``--probe`` derives its ``choices`` from the table, so the two can never
    disagree -- which also means a name vanishing from BOTH at once would go
    unnoticed. Spelling the set out here is the third party that makes that a
    failure rather than a quiet narrowing of the harness.
    """
    assert set(_probe_runner.PROBES) == EXPECTED_PROBE_NAMES


def test_every_probe_table_row_resolves_to_its_like_named_function():
    """Forward drift protection: a row must point at the function it names.

    Asserted by ``__name__`` rather than by callability -- a swapped row is
    callable, runs, and returns a plausible verdict for the wrong check, which
    is precisely the kind of false verdict this corpus exists to freeze.
    """
    mismatched = {
        name: getattr(fn, "__name__", repr(fn))
        for name, fn in _probe_runner.PROBES.items()
        if getattr(fn, "__name__", None) != f"probe_{name}"
    }
    assert not mismatched, (
        f"probe table rows point at the wrong function: {mismatched}"
    )


def test_every_probe_function_is_registered_in_the_table():
    """Reverse drift protection: an unregistered probe is unreachable code.

    A ``probe_*`` function with no row cannot be selected by ``--probe``, so it
    stops being part of the harness while still reading as a live check. ``t2``
    is the live example of why this direction is needed rather than theoretical:
    no test module invokes it, so nothing else in the suite would notice it
    dropping out.

    Filtered by ``__module__`` so an imported helper whose name happens to carry
    the prefix cannot masquerade as a probe.
    """
    defined = {
        name[len("probe_"):]
        for name, obj in vars(_probe_runner).items()
        if name.startswith("probe_") and callable(obj)
        and getattr(obj, "__module__", None) == _probe_runner.__name__
    }
    unregistered = defined - set(_probe_runner.PROBES)
    assert not unregistered, (
        f"probe functions missing from the dispatch table (unreachable via "
        f"--probe): {sorted(unregistered)}"
    )
