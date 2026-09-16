"""False-positive avoidance, named accepted-gap pins, and file-readability
edge cases for `shared/scripts/lib/triage_plain_append_scan.py`.

Split out of `test_triage_plain_append_scan.py` once it crossed 300 lines,
the same reason `test_triage_precondition_registry.py` was split from
`test_triage_precondition_callers.py`. That sibling file keeps the core
call-shape detection tests (plain call, attribute call, aliasing); this
file keeps import-shape false positives, named accepted-gap pins, and
file-readability corner cases. The scope-chain/shadowing regression tests
(rounds 5-8 external review) live in their own sibling,
`test_triage_plain_append_scope.py`, split out for the same reason once
this file crossed 300 lines again. All fixtures are synthetic (`tmp_path`).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.triage_plain_append_scan import (  # noqa: E402
    find_plain_append_callers,
    find_unparseable_files,
)


def test_a_same_named_import_from_an_unrelated_module_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """External code review (GLM, low) found this gap: an earlier revision
    matched the bare name `append_triage_item` regardless of WHERE it was
    imported from, so an unrelated function that merely shares the name
    (a re-export wrapper, a same-named helper in a different module) was
    flagged as a triage violation. The import must resolve to the `triage`
    module specifically.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    unrelated = scripts_dir / "unrelated_producer.py"
    unrelated.write_text(
        "from some_other_module import append_triage_item\n"
        "def emit(root):\n"
        "    return append_triage_item(root)\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()


def test_a_same_named_method_on_an_unrelated_object_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """External code review (both providers, low) found this gap: an earlier
    revision matched `obj.append_triage_item(...)` for ANY `obj`, so an
    unrelated object's own same-named method (`writer.append_triage_item(...)`)
    was flagged. The attribute's object must resolve to a name this file
    actually bound via `import triage`.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    unrelated = scripts_dir / "unrelated_method_producer.py"
    unrelated.write_text(
        "class Writer:\n"
        "    def append_triage_item(self, *a, **k):\n"
        "        pass\n"
        "def emit(writer):\n"
        "    return writer.append_triage_item('x')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()


def test_a_star_import_of_the_bare_name_is_still_found(tmp_path: Path) -> None:
    """`from triage import *` followed by a bare `append_triage_item(...)`
    call must be caught.

    Round 4 external review (GLM, medium) found this gap: `alias.name == "*"`
    never equals the literal target name, so an earlier revision's exact-name
    match silently missed a star-imported call -- a real false negative, not
    one of the module's named accepted gaps.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    starred = scripts_dir / "star_import_producer.py"
    starred.write_text(
        "from triage import *\n"
        "def emit(root):\n"
        "    return append_triage_item(root, source='x', severity='low', "
        "kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == {"shared/scripts/star_import_producer.py"}


def test_a_star_import_of_an_unrelated_module_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """The star-import fix above must stay scoped to the `triage` module --
    a star import of an unrelated module must not itself trip the scan.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    starred = scripts_dir / "unrelated_star_import_producer.py"
    starred.write_text(
        "from some_other_module import *\n"
        "def emit(root):\n"
        "    return append_triage_item(root)\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()


def test_a_package_qualified_import_is_a_named_accepted_gap(
    tmp_path: Path,
) -> None:
    """Documents, and asserts, the module docstring's limit #1: a
    package-qualified import of `triage` itself (as opposed to the bare
    `import triage` every real producer in this repo uses) is NOT detected.

    This is a POSITIVE pin of a known limitation, not a bug report -- round 3
    external review (both providers) asked for the accepted gap to be
    verified with a test, not just asserted in prose. If this test ever
    starts failing (i.e. the call IS found), `find_plain_append_callers`
    grew qualified-import resolution and this test's assertion -- not the
    module docstring's limit #1 -- is what needs updating.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    qualified = scripts_dir / "qualified_import_producer.py"
    qualified.write_text(
        "from shared.scripts import triage\n"
        "def emit(root):\n"
        "    return triage.append_triage_item(root, source='x', "
        "severity='low', kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set(), (
        "find_plain_append_callers now resolves a package-qualified triage "
        "import -- update the module docstring's limit #1 (it is no longer "
        "an accepted gap) instead of treating this failure as a regression"
    )


def _rogue_producer(root: Path, relative_dir: str) -> None:
    excluded_dir = root / "shared" / "scripts" / relative_dir
    excluded_dir.mkdir(parents=True)
    (excluded_dir / "rogue_producer.py").write_text(
        "import triage\n"
        "def emit(root):\n"
        "    return triage.append_triage_item(root, source='x', "
        "severity='low', kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )


def test_a_producer_under_venv_is_excluded_from_the_scan(tmp_path: Path) -> None:
    """Round 11 (external code review, req3-06 e5, low): the directory-name
    EXCLUSION itself was never positively pinned -- only the package-
    qualified-import gap above was. If a future edit dropped `.venv` from
    `EXCLUDED_PARTS`, nothing would catch a real producer's registry test
    turning into a full site-packages scan. This is a positive pin of the
    EXCLUSION, not the detection: a plain-append call under `.venv/` must
    stay invisible, the same as if it were never scanned at all.
    """
    _rogue_producer(tmp_path, ".venv/some_package")
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set(), (
        "a producer under .venv/ was found -- EXCLUDED_PARTS no longer "
        "excludes .venv, or the exclusion mechanism itself changed"
    )


def test_a_producer_under_a_tests_dir_is_excluded_from_the_scan(
    tmp_path: Path,
) -> None:
    """Sibling to the `.venv` pin above -- `tests/` is the OTHER directory
    name this scanner's own registry test suite lives under, so an
    exclusion regression there would be the most self-defeating possible
    failure: this scanner's own tests would start tripping it.
    """
    _rogue_producer(tmp_path, "tests")
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set(), (
        "a producer under tests/ was found -- EXCLUDED_PARTS no longer "
        "excludes tests/, or the exclusion mechanism itself changed"
    )


def test_a_relative_import_of_an_unrelated_function_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """Round 2 external review (GLM, low) caught a real bug: an earlier
    revision matched `ImportFrom.module in {"triage", None}`, which accepted
    ANY relative import unconditionally -- including a same-named function
    from a completely unrelated relative module. Module scoping must be
    exact, not "triage, or anything with no dotted module name at all".
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    unrelated = scripts_dir / "relative_import_producer.py"
    unrelated.write_text(
        "from .utils import append_triage_item\n"
        "def emit(root):\n"
        "    return append_triage_item(root)\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()


def test_a_relative_import_literally_named_triage_is_not_the_real_module(
    tmp_path: Path,
) -> None:
    """Round 9 external review (GLM, medium): an earlier revision compared
    only `node.module == "triage"`, so a RELATIVE import that happens to be
    literally named `.triage` (`from .triage import append_triage_item`,
    `level=1`) matched as if it were the real, absolute `triage` module --
    even though no real producer in this repo has ever used a relative
    import (module docstring limit #1's own empirical grep). `node.level ==
    0` is now required for a match.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    unrelated = scripts_dir / "relative_triage_named_producer.py"
    unrelated.write_text(
        "from .triage import append_triage_item\n"
        "def emit(root):\n"
        "    return append_triage_item(root)\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()


def test_the_reverse_guard_actually_fails_on_an_unparseable_file(
    tmp_path: Path,
) -> None:
    """Prove `find_unparseable_files` can fail, not just pass."""
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    broken = scripts_dir / "broken_producer.py"
    broken.write_text("def emit(:\n    pass\n", encoding="utf-8")  # syntax error
    found = find_unparseable_files(tmp_path, bases=("shared/scripts",))
    assert found == {"shared/scripts/broken_producer.py"}


def test_a_declared_non_utf8_encoding_is_honoured_not_silently_dropped(
    tmp_path: Path,
) -> None:
    """External code review (openai, low): a PEP 263 encoding declaration
    must be honoured -- a Latin-1-declared file must be readable AND its
    call site found, not silently treated as unparseable just because it
    is not valid UTF-8.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    latin1 = scripts_dir / "latin1_producer.py"
    source = (
        "# -*- coding: latin-1 -*-\n"
        "# a comment with a Latin-1-only byte: \xe9\n"
        "from triage import append_triage_item\n"
        "def emit(root):\n"
        "    return append_triage_item(root, source='x', severity='low', "
        "kind='bug', title='t', detail='d')\n"
    )
    latin1.write_bytes(source.encode("latin-1"))
    assert find_unparseable_files(tmp_path, bases=("shared/scripts",)) == set()
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == {"shared/scripts/latin1_producer.py"}
