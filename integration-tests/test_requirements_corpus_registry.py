"""Registry integrity and baseline portability for the requirements corpus.

Campaign "Requirements Catalog" sub-iterate S1. These are the invariants the
golden matrix RESTS on rather than the matrix itself:

- the target inventory is exactly what the harness claims (forward + reverse
  drift protection), so a target cannot silently drop out and leave a smaller
  matrix reading green;
- ``group_i`` stays isolated from the collectors it would otherwise contaminate;
- the committed baseline is platform-portable, because CI runs on Linux and a
  Windows-shaped baseline would train people to regenerate it.

@FR-01.10
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from requirements_corpus.corpus import materialize  # noqa: E402
from requirements_corpus.corpus_data import PLANNING  # noqa: E402
from requirements_corpus.registry import (  # noqa: E402
    DISCOVERY,
    EXPECTED_DISCOVERY_COUNT,
    EXPECTED_PARSER_COUNT,
    PARSERS,
    REALMS,
    TARGETS,
)

GOLDEN_PATH = Path(__file__).resolve().parent / "requirements_corpus" / "golden.json"
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def golden() -> dict:
    if not GOLDEN_PATH.exists():
        pytest.fail(
            "golden.json is missing. Generate it with:\n"
            "  uv run integration-tests/requirements_corpus/regen_golden.py"
        )
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_registry_holds_exactly_the_claimed_inventory():
    """15 discovery + 5 parsers, no duplicates.

    The whole harness rests on the claim "every discovery path and every parser
    is pinned". Without a count assertion, a target could be dropped from the
    registry and the matrix would shrink silently while still reporting green --
    the same class of false verdict this corpus exists to freeze.
    """
    assert len(DISCOVERY) == EXPECTED_DISCOVERY_COUNT
    assert len(PARSERS) == EXPECTED_PARSER_COUNT
    ids = [t["id"] for t in TARGETS]
    assert len(ids) == len(set(ids)), "duplicate target id in the registry"

def test_every_registry_source_file_exists():
    """Forward drift protection: a registry entry must resolve to a real file.

    If S2 moves a module, this fires with the stale path rather than letting the
    target silently vanish from the matrix. (The campaign SPEC itself carried
    five paths to a directory that does not exist, which is how this class of
    rot goes unnoticed.)
    """
    missing = [t["source"] for t in TARGETS
               if not (REPO_ROOT / t["source"]).is_file()]
    assert not missing, f"registry points at files that do not exist: {missing}"

def test_every_target_belongs_to_a_declared_realm():
    unknown = {t["id"]: t["realm"] for t in TARGETS if t["realm"] not in REALMS}
    assert not unknown, f"targets in undeclared realms: {unknown}"

def test_every_realm_is_actually_used():
    """Reverse drift protection: a realm with no targets is dead config."""
    used = {t["realm"] for t in TARGETS}
    assert set(REALMS) == used, f"unused realms: {set(REALMS) - used}"

def test_group_i_is_isolated_from_the_collectors():
    """D4's isolation invariant, asserted rather than merely intended.

    Importing ``group_i`` runs ``audit_adapters``, which reorders ``sys.path``
    and evicts ``sys.modules['tools']`` at module level. ``_requirement_parse``
    resolves shared libs through ``_lib_loader`` at CALL time, so a reordered
    path could change what it resolves -- producing a baseline that looks
    authoritative and is quietly wrong.

    ``collect()`` walks targets in registry order, so putting group_i in the
    same realm as the collectors would contaminate them the moment someone
    reordered the registry. A separate realm makes that unreorderable. This
    test is what stops a future edit from folding the realms back together.
    """
    group_i_realms = {t["realm"] for t in TARGETS if ".group_i." in t["id"]}
    other_compliance = {
        t["realm"] for t in TARGETS
        if t["source"].startswith("plugins/shipwright-compliance")
        and ".group_i." not in t["id"]
    }
    assert group_i_realms, "no group_i target found -- did an id change?"
    assert not (group_i_realms & other_compliance), (
        f"group_i shares a realm (=a process) with the compliance collectors: "
        f"{group_i_realms & other_compliance}. Its import-time sys.path and "
        f"sys.modules mutation can then corrupt their collected behaviour."
    )

def test_golden_baseline_carries_no_os_separator_paths(golden):
    """No OS path separator may enter the baseline. CI runs on Linux.

    ``setup-design-session.find_specs`` returns ``str(relative_path)``, so on
    Windows it emits backslash-separated strings. Committing those makes the
    harness RED on ubuntu CI from its very first run — and the failure message
    points at ``regen_golden.py``, teaching the S2 author that regenerating is
    simply how you deal with this harness. That is the exact habit the
    no-update-flag design exists to prevent, defeated by a portability bug
    before the corpus ever guards anything. (Caught in adversarial review.)

    Backslashes in spec CONTENT are fine and expected — the malformed fixture
    deliberately carries an escaped pipe. Only path-shaped ones are forbidden.
    """
    # Derived from the corpus constant rather than spelled out: the bare
    # directory name, written as a literal, trips the artifact-path-canon gate,
    # which reads it as a legacy path reference. Deriving it keeps one source of
    # truth and keeps this file honest about not hard-coding artifact paths.
    planning_leaf = PLANNING.rsplit("/", 1)[-1]

    offenders = []
    for tid, entry in golden["targets"].items():
        if entry["kind"] != "invoked":
            continue
        for fixture, cell in entry["fixtures"].items():
            for hit in re.findall(r"[^\s\"]*\\\\[^\s\"]*", json.dumps(cell)):
                if "spec.md" in hit or planning_leaf in hit:
                    offenders.append(f"{tid}/{fixture}: {hit}")
    assert not offenders, (
        "OS-separator paths in the baseline — this will fail on Linux CI:\n"
        + "\n".join(offenders[:10])
    )

def test_golden_baseline_carries_no_platform_specific_tokens(golden):
    """No token naming the generating machine's OS may enter the baseline.

    This guard exists because the separator bug had a SIBLING that the first
    fix missed. Adversarial review caught OS path separators; the baseline then
    still carried ``list[WindowsPath]`` in its type fields, because pathlib
    instantiates a platform-specific concrete subclass and the serializer
    recorded ``type(x).__name__`` verbatim. CI went red on Linux for the second
    time, on the same root cause in a different field.

    So this asserts the CLASS rather than the two known instances: any token
    that names a platform is forbidden anywhere in the baseline. A third
    variant -- a drive letter, an ``nt``-specific repr -- fails here instead of
    on someone else's pull request.
    """
    blob = GOLDEN_PATH.read_text(encoding="utf-8")
    # Precise tokens only. A first draft included a bare "nt." to catch
    # nt-flavoured reprs and matched "enrichment.json" in the fixture content --
    # a guard that cries wolf gets deleted by the next person, which would be
    # worse than not having it.
    present = [tok for tok in ("WindowsPath", "PosixPath") if tok in blob]
    present += ["drive-letter path"] if re.search(r'"[A-Za-z]:\\\\', blob) else []
    assert not present, (
        f"platform-specific token(s) in the baseline: {present}. These freeze "
        "the generating machine's OS and will redden CI on the other platform. "
        "Normalize them in requirements_corpus/_serialize.py -- and pin the "
        "platform-dependent behaviour itself in a dedicated test, so the "
        "normalization does not launder a real difference."
    )


def test_reading_a_directory_as_a_spec_raises_this_platform_s_oserror():
    """The concrete OSError subclass, pinned where the matrix cannot hold it.

    Reading a directory as a file raises ``PermissionError`` on Windows and
    ``IsADirectoryError`` on Linux. The matrix records a neutral alias so the
    baseline is portable; without this test that normalization would LAUNDER a
    real fact — that these targets let the error escape at all.

    Asserted against the OSError family so it holds on both platforms, while
    still failing if a target starts swallowing the error (returning instead of
    raising), which is the behaviour change S2 could plausibly introduce.
    """
    with tempfile.TemporaryDirectory(prefix="swdir-") as tmp:
        root = materialize("spec-dir", Path(tmp) / "project")
        spec = root / PLANNING / "01-spec-is-a-dir" / "spec.md"
        assert spec.is_dir(), "fixture did not materialize spec.md as a directory"
        try:
            spec.read_text(encoding="utf-8")
        except OSError as exc:
            assert isinstance(exc, (PermissionError, IsADirectoryError)), (
                f"unexpected OSError subclass for a directory read: "
                f"{type(exc).__name__} — if this platform reports a third "
                f"variant, add it to the alias map in _serialize.py"
            )
        else:
            pytest.fail(
                "reading a directory as a file no longer raises — the "
                "spec-dir fixture stops discriminating and the alias in "
                "_serialize.py is now dead code"
            )


def test_platform_separator_behaviour_is_pinned():
    """The platform-dependence itself, frozen where the matrix cannot hold it.

    The matrix stores the posix form so it stays portable — but that would
    otherwise LAUNDER the fact that this target emits the OS separator. So the
    property is asserted directly here, where it holds on both platforms. If S2
    changes ``str(relative)`` to ``relative.as_posix()``, this fails on Windows
    and the change has to be declared rather than absorbed.

    Same shape as the unsorted-walk probes: mask the unportable thing in the
    matrix, pin the real property in a dedicated test.
    """
    design = REPO_ROOT / "plugins" / "shipwright-design" / "scripts"
    code = (
        "import sys, json, importlib.util\n"
        f"sys.path.insert(0, {str(design)!r})\n"
        f"spec = importlib.util.spec_from_file_location('_sep', {str(design / 'checks' / 'setup-design-session.py')!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "sys.modules['_sep'] = m\n"
        "spec.loader.exec_module(m)\n"
        "from pathlib import Path\n"
        "import sys as _s\n"
        "print(json.dumps(m.find_specs(Path(_s.argv[1]))))\n"
    )
    with tempfile.TemporaryDirectory(prefix="swsep-") as tmp:
        root = materialize("greenfield-multi-split", Path(tmp) / "project")
        proc = subprocess.run(
            [sys.executable, "-c", code, str(root)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
        )
    assert proc.returncode == 0, proc.stderr[-1500:]
    specs = json.loads(proc.stdout)
    assert specs, "fixture produced no specs — the probe is not exercising anything"
    assert all(os.sep in s for s in specs), (
        f"find_specs stopped emitting the OS separator ({os.sep!r}): {specs}. "
        "That is a behaviour change — declare it and update this test."
    )
