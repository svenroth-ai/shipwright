"""Every plain `append_triage_item()` call site is a deliberate, registered exception.

FR-01.14 row #1's mechanisable half, closed
(`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`):
"the producer contract has no gate, and a new producer calling the plain
append writes duplicates freely." The row itself named the oracle -- "a
meta-test over the call sites" -- and this is it, in the exact
registry-plus-reverse-guard shape `test_triage_precondition_registry.py`
already established for the sibling `mark_status` flip-site concern
(`test_no_unregistered_module_flips_status`).

The AST scanner ITSELF lives in `shared/scripts/lib/triage_plain_append_scan.py`
(its own module docstring carries the scope justification and the three
named, accepted detection limits) plus its scope-chain engine, split into
the sibling `triage_plain_append_scope.py` once the scanner file crossed 300
lines; its own unit-level detection behaviour (aliasing, false-positive
shapes, unparseable-file handling) is pinned in the sibling
`test_triage_plain_append_scan.py` and
`test_triage_plain_append_scan_edge_cases.py`, split out from this file for
the same reason -- the registry file's job is only the allowlist and the
reverse-drift guard against the LIVE repo, not the scanner's own edge cases.

**What was found before writing a line of enforcement (verified, not
assumed):** exactly one production call site anywhere in the repo calls the
plain, non-deduplicating `append_triage_item` -- `triage_add.py`, the MANUAL
operator CLI ("Manual triage card creation CLI", its own module docstring).
A human typing one command is not "simultaneous producers"; the race the
mechanisable half worries about is a *background, automated* producer
racing another instance of itself, and every automated producer already in
the tree (github_triage's consumer, check_drift, phase_quality's
`_triage_bundle`, security's `security_triage_emit`, test's
`warning_followups`/`performance_check`/`journey_coverage`, adopt's two
baseline seeders, `external_review_degraded`, `check_required_checks`,
`suite_race_triage`, `artifact_sync`) already calls
`append_triage_item_idempotent`. That discipline held everywhere it mattered
-- but nothing MADE it hold, which is exactly what "no gate" means. This file
makes it self-enforcing: a tenth automated producer added later must call the
idempotent form, or its call to the plain one fails this test by name and
must be explicitly, visibly registered here -- the same allowlist discipline
`shipwright_bloat_baseline.json` uses for a LOC crossing.
"""

from __future__ import annotations

import sys
import tokenize
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.triage_plain_append_scan import (  # noqa: E402
    find_plain_append_callers,
    find_unparseable_files,
)

#: The one legitimate exception -- documented, not silent. A manual CLI
#: invoked once by a human operator carries none of the concurrent-producer
#: race the idempotent path exists to close.
ALLOWED_PLAIN_APPEND_CALLERS = frozenset({
    "shared/scripts/tools/triage_add.py",
})


def _assert_registry_matches(found: set[str]) -> None:
    """The registry comparison itself -- extracted so the reverse-guard
    tests below can call this EXACT code path and prove IT can fail, not a
    separately re-typed assertion that could silently drift from the live
    guard (round 9 external review, openai, medium: a prior revision's
    "reverse guard" tests only re-asserted `found != registered` inline,
    so weakening this function to e.g. `found <= registered` would have
    passed every test in this file undetected).
    """
    registered = set(ALLOWED_PLAIN_APPEND_CALLERS)
    assert found == registered, (
        f"unregistered plain append_triage_item() caller(s): "
        f"{sorted(found - registered)}; "
        f"stale registry entries (no longer call it): "
        f"{sorted(registered - found)}. "
        "A new AUTOMATED producer must call append_triage_item_idempotent() "
        "instead; a genuinely manual, human-driven caller may register here."
    )


def test_no_unregistered_module_calls_plain_append() -> None:
    """REVERSE drift protection -- a tenth producer must not appear unnoticed.

    Mirrors `test_triage_precondition_registry.py::
    test_no_unregistered_module_flips_status` for the sibling `mark_status`
    concern: same shape, same guarantee -- a call site not on the allowlist
    fails this test by name, not silently, and a registry entry that no
    longer calls it is surfaced as stale rather than left to rot.
    """
    _assert_registry_matches(find_plain_append_callers(_REPO_ROOT))


def test_no_unparseable_file_is_a_silent_scan_gap() -> None:
    """A file this scanner cannot read/parse is a FINDING, not a silent pass.

    External code review (both providers, low) found that an earlier
    revision's silent `except: return None` let a broken-mid-edit or
    wrong-encoding-declared file hide a violation invisibly. Expected empty
    in a healthy tree; a non-empty result names the file(s) a human must
    look at before the reverse-drift guard's "found == registered" claim
    above can be trusted. `find_unparseable_files`'s own detection behaviour
    (what counts as unparseable, PEP 263 handling) is unit-tested in
    `test_triage_plain_append_scan.py`; this is the LIVE-repo pin.
    """
    unparseable = find_unparseable_files(_REPO_ROOT)
    assert unparseable == set(), (
        f"{sorted(unparseable)} could not be read/parsed by the plain-append "
        "scan -- a call hidden there would be invisible to the registry test"
    )


def test_every_registered_caller_is_documented_as_manual() -> None:
    """A RATIONALE guard, not a behavioral one -- deliberately trivial.

    External plan review (both providers) correctly flagged a wording-based
    pin as brittle if it were trying to PROVE the exception still holds. It
    is not: it exists only so a cosmetic rewording of a registered caller
    cannot silently drop the one sentence that justifies its presence in
    `ALLOWED_PLAIN_APPEND_CALLERS` without a human noticing. Someone widening
    a registered CLI into a scheduled/background caller can still update its
    text and the registry together -- the guard's job is to force that to be
    a conscious edit, not to detect the widening on its own.

    Loops over EVERY registered entry, not just one (round 3 external
    review, GLM, low): checking only `next(iter(...))` would silently stop
    covering a second registration the moment one existed. Reads via
    `tokenize.open()`, not a bare `read_text(encoding="utf-8")` (round 4
    external review, GLM, low): a registered file legitimately declared in a
    non-UTF-8 encoding -- exactly the case `triage_plain_append_scan.py`
    itself goes out of its way to honour -- must not crash this pin with an
    opaque `UnicodeDecodeError` instead of the intended assertion message.
    """
    for entry in ALLOWED_PLAIN_APPEND_CALLERS:
        # Round 6 external review (GLM, low): a registered entry that is
        # later deleted, renamed, or left with a mangled encoding
        # declaration must fail with THIS guard's own explanation, not an
        # opaque FileNotFoundError/SyntaxError traceback that hides why the
        # registry test cares about the file at all.
        try:
            with tokenize.open(_REPO_ROOT / entry) as fh:
                text = fh.read()
        except (OSError, SyntaxError, UnicodeDecodeError, tokenize.TokenError) as exc:
            raise AssertionError(
                f"registered entry {entry!r} could not be read ({exc!r}) -- "
                "a RATIONALE guard cannot check wording it cannot read; fix "
                "the registry entry or the file before trusting this pin"
            ) from exc
        assert "manual" in text.lower(), (
            f"{entry} no longer describes itself as a manual CLI in its own "
            "text -- this is a RATIONALE guard: re-check by hand whether the "
            "file still qualifies for the plain-append exception before "
            "touching the wording that keeps this test green"
        )


def test_the_reverse_guard_actually_fails_on_an_unregistered_caller(
    tmp_path: Path,
) -> None:
    """Prove the guard above can fail, not just pass -- the same discipline
    as `test_adr_index_producers.py::test_drift_guard_actually_fails_on_a_stale_index`.
    A guard nobody has watched fail is not evidence.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    rogue = scripts_dir / "rogue_producer.py"
    rogue.write_text(
        "from triage import append_triage_item\n"
        "def emit(root):\n"
        "    return append_triage_item(root, source='x', severity='low', "
        "kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == {"shared/scripts/rogue_producer.py"}
    # Round 8 (GLM, low) then round 9 (openai, medium) external review:
    # proving the SCANNER finds the rogue file is not the same as proving
    # the live guard's OWN comparison would reject it -- call the exact
    # function `test_no_unregistered_module_calls_plain_append` calls, and
    # prove it raises for this rogue set.
    with pytest.raises(AssertionError):
        _assert_registry_matches(found)


def test_the_reverse_guard_fires_from_a_different_top_level_directory_too(
    tmp_path: Path,
) -> None:
    """Round 6 external review (GLM, medium): the proof above only scans
    `shared/scripts`, never the DEFAULT, repo-root `bases`
    (`SEARCH_BASES = (".",)`) this file's own registry test actually uses.
    The repo-root widening was the entire point of an earlier external-review
    round ("accidentally true, not structurally guaranteed") -- a rogue
    producer in an unrelated top-level directory, scanned with the DEFAULT
    bases (no `bases=` override), must still be found, or a future change
    that quietly re-narrows `SEARCH_BASES` would pass every test in this
    file undetected.
    """
    plugin_dir = tmp_path / "plugins" / "rogue_plugin" / "scripts"
    plugin_dir.mkdir(parents=True)
    rogue = plugin_dir / "rogue_producer.py"
    rogue.write_text(
        "from triage import append_triage_item\n"
        "def emit(root):\n"
        "    return append_triage_item(root, source='x', severity='low', "
        "kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path)
    assert found == {"plugins/rogue_plugin/scripts/rogue_producer.py"}
