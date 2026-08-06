"""The read boundary: absent, usable, or unusable — and never the wrong one.

``config_io.load_run_config`` answered ``{}`` for two different questions —
*"there is no config"* and *"there is a config but I cannot use it"*. This suite
covers the source layer that now tells them apart; the consequences for a run
are in ``test_runconfig_corrupt_fail_closed.py`` and the message contract in
``test_runconfig_corrupt_message.py``. Decision and rationale:
``.shipwright/planning/iterate/iterate-2026-08-05-standalone-flag-corrupt-config.md``
"""
import inspect
import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))  # for runconfig_corrupt_shapes

import orchestrator  # noqa: E402,F401 — installs the ``orchestrator`` shim namespace
from orchestrator_pkg import config_io  # noqa: E402
from orchestrator_pkg.config_io import RunConfigUnreadable  # noqa: E402
from orchestrator_pkg.constants import CONFIG_NAME  # noqa: E402
from runconfig_corrupt_shapes import (  # noqa: E402
    USABLE_CONTENT,
    UNUSABLE_CONTENT,
    raiser,
    real_config,
    write,
)


# --------------------------------------------------------------------------- #
# AC1 — total at the read boundary, and presence is not truthiness
# --------------------------------------------------------------------------- #

def test_absent_is_not_an_error(tmp_path):
    """A first run has no config: a valid state, not a fault."""
    assert config_io.read_run_config(tmp_path) == ({}, False)


@pytest.mark.parametrize("name", sorted(UNUSABLE_CONTENT))
def test_raises_on_every_unusable_shape(tmp_path, name):
    write(tmp_path, UNUSABLE_CONTENT[name])
    with pytest.raises(RunConfigUnreadable):
        config_io.read_run_config(tmp_path)


@pytest.mark.parametrize("name", sorted(USABLE_CONTENT))
def test_accepts_every_usable_shape(tmp_path, name):
    write(tmp_path, USABLE_CONTENT[name])
    config, present = config_io.read_run_config(tmp_path)
    assert present is True
    assert isinstance(config, dict)


def test_present_empty_object_is_present_not_absent(tmp_path):
    """The truthiness door. Only the absence of the FILE is absence."""
    write(tmp_path, "{}")
    config, present = config_io.read_run_config(tmp_path)
    assert config == {}
    assert present is True, "'{}' is falsy but the file is there"


def test_absence_comes_from_the_read_not_from_a_probe(tmp_path):
    """A ``path.exists()`` then read can straddle a concurrent delete."""
    write(tmp_path, "{}")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(config_io, "durable_read_text", raiser(FileNotFoundError(2, "gone")))
    try:
        assert config_io.read_run_config(tmp_path) == ({}, False)
    finally:
        monkeypatch.undo()


# --------------------------------------------------------------------------- #
# AC2 — a category, and advice that fits it
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("content", "category"),
    [("{oops", "parse"), ("", "parse"), ("null", "shape"), ("[]", "shape"), ("123", "shape")],
)
def test_carries_a_category(tmp_path, content, category):
    write(tmp_path, content)
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    assert excinfo.value.category == category


def test_a_utf8_bom_is_tolerated_not_treated_as_corruption(tmp_path):
    """PowerShell 5.1 `Out-File -Encoding utf8` and VS Code's `utf8bom` emit one
    on this repo's primary platform, and five sibling readers already moved to
    utf-8-sig for it. Under fail-closed, not stripping it turns an INVISIBLE byte
    into a wedged run, reported at "line 1 column 1" of a file that looks valid
    in every editor (Stage-3)."""
    (tmp_path / CONFIG_NAME).write_bytes(
        b"\xef\xbb\xbf" + json.dumps({"standalone": False, "pipeline": ["plan"]}).encode()
    )
    config, present = config_io.read_run_config(tmp_path)
    assert present is True
    assert config["standalone"] is False


def test_non_utf8_classifies_as_decode(tmp_path):
    (tmp_path / CONFIG_NAME).write_bytes(b'{"standalone": fa\xff\xfelse}')
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    assert excinfo.value.category == "decode"


def test_a_file_where_the_project_root_should_be_reads_as_absent(tmp_path):
    """``Path.exists()`` — the old absence test — answered False here, so the
    tolerant reader must keep degrading, not start raising (Stage-3)."""
    not_a_dir = tmp_path / "afile"
    not_a_dir.write_text("x", encoding="utf-8")
    assert config_io.read_run_config(not_a_dir) == ({}, False)
    assert config_io.load_run_config(not_a_dir) == {}


def test_io_failure_classifies_as_io(tmp_path, monkeypatch):
    write(tmp_path, "{}")
    monkeypatch.setattr(config_io, "durable_read_text", raiser(PermissionError(13, "denied")))
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    assert excinfo.value.category == "io"


def test_deeply_nested_json_classifies_as_parse(tmp_path):
    """RecursionError, NOT JSONDecodeError, past json's nesting limit."""
    write(tmp_path, "[" * 20000 + "]" * 20000)
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    assert excinfo.value.category == "parse"


def test_io_does_not_tell_the_operator_to_delete_the_file(tmp_path, monkeypatch):
    """Recreating is wrong advice here: the file is fine, the access is not."""
    write(tmp_path, "{}")
    monkeypatch.setattr(config_io, "durable_read_text", raiser(PermissionError(13, "denied")))
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    rendered = str(excinfo.value).lower()
    assert "/shipwright-run" not in rendered
    assert "permission" in rendered


def test_bad_content_tells_the_operator_how_to_recover_without_losing_it(tmp_path):
    """Both halves matter: how to recreate, AND that re-running is itself what
    destroys the file — `write-config` replaces it whether or not it was deleted
    first, so 'delete it and re-run' alone implied the bytes were safe until the
    operator chose otherwise (Stage-3 review)."""
    write(tmp_path, "{oops")
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    rendered = str(excinfo.value)
    assert "/shipwright-run" in rendered
    assert "REPLACES" in rendered


# --------------------------------------------------------------------------- #
# AC3 — the tolerant reader keeps its contract
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(UNUSABLE_CONTENT))
def test_tolerant_reader_returns_empty_for_bad_content(tmp_path, name):
    """Unchanged for parse; NEW for shape (a non-object was returned raw)."""
    write(tmp_path, UNUSABLE_CONTENT[name])
    assert config_io.load_run_config(tmp_path) == {}


def test_tolerant_reader_propagates_decode_as_its_own_type(tmp_path):
    """``test_read_gives_up_loudly_rather_than_inventing_an_empty_config`` pins
    that a decode failure never becomes an empty config; it must not be re-typed
    into RunConfigUnreadable either."""
    (tmp_path / CONFIG_NAME).write_bytes(b'{"a": \xff\xfe}')
    with pytest.raises(UnicodeDecodeError):
        config_io.load_run_config(tmp_path)


@pytest.mark.parametrize(
    "exc",
    [PermissionError(13, "denied"), IsADirectoryError(21, "is a directory")],
)
def test_tolerant_reader_propagates_oserror_as_its_own_type(tmp_path, monkeypatch, exc):
    """The concrete type, not the wrapper: a caller catching ``PermissionError``
    must still catch it after the strict/tolerant split."""
    write(tmp_path, "{}")
    monkeypatch.setattr(config_io, "durable_read_text", raiser(exc))
    with pytest.raises(type(exc)):
        config_io.load_run_config(tmp_path)


@pytest.mark.parametrize("category", ["decode", "io"])
def test_tolerant_reader_survives_an_unreadable_with_no_original(
    tmp_path, monkeypatch, category,
):
    """Reading the original off ``__cause__`` would turn a raise site that forgot
    ``from exc`` into a TypeError inside the display surfaces (Stage-2)."""
    write(tmp_path, "{}")
    orphan = RunConfigUnreadable(tmp_path / CONFIG_NAME, "no cause", category)
    assert orphan.original is None
    monkeypatch.setattr(config_io, "_read_parse_shape", raiser(orphan))
    with pytest.raises(RunConfigUnreadable):
        config_io.load_run_config(tmp_path)


def test_message_is_bounded_even_for_a_very_long_path(tmp_path):
    """``message`` embeds the path: unbounded there would defeat the cap via the
    one field carrying what both others carry (Stage-2 review)."""
    long_path = Path("C:/" + "d" * 4000) / CONFIG_NAME
    exc = RunConfigUnreadable(long_path, "boom", "parse")
    assert len(exc.payload()["path"]) <= config_io.MAX_DETAIL_CHARS
    assert len(str(exc)) <= 4 * config_io.MAX_DETAIL_CHARS


def test_load_run_config_signature_is_unchanged():
    """No new keyword. A caller passing ``migrate`` keeps working exactly as
    before; the strict behaviour lives in a separate function on purpose."""
    assert list(inspect.signature(config_io.load_run_config).parameters) == [
        "project_root", "migrate",
    ]


# --------------------------------------------------------------------------- #
# AC13 — one shared read boundary, so the two readers cannot drift
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted({**UNUSABLE_CONTENT, **USABLE_CONTENT}))
def test_the_two_readers_never_disagree_about_usability(tmp_path, name):
    """They differ only in DISPOSAL, never in DETECTION."""
    content = {**UNUSABLE_CONTENT, **USABLE_CONTENT}[name]
    write(tmp_path, content)

    try:
        config_io.read_run_config(tmp_path)
        strict_ok = True
    except RunConfigUnreadable:
        strict_ok = False

    tolerant_ok = config_io.load_run_config(tmp_path) != {} or content.strip() == "{}"
    assert strict_ok == tolerant_ok, f"readers disagree about {name!r}"


@pytest.mark.parametrize("category", ["decode", "io"])
def test_the_readers_agree_on_the_categories_that_actually_diverge(
    tmp_path, monkeypatch, category,
):
    """The table above is text-only, so it never reaches ``decode`` / ``io`` —
    the only two categories where the readers branch differently, i.e. the only
    two that can drift (Stage-3). Both must call the file unusable; only the
    TYPE they raise may differ."""
    if category == "decode":
        (tmp_path / CONFIG_NAME).write_bytes(b'{"a": \xff\xfe}')
        concrete = UnicodeDecodeError
    else:
        write(tmp_path, "{}")
        monkeypatch.setattr(
            config_io, "durable_read_text", raiser(PermissionError(13, "denied")))
        concrete = PermissionError

    with pytest.raises(RunConfigUnreadable) as strict:
        config_io.read_run_config(tmp_path)
    assert strict.value.category == category

    with pytest.raises(concrete):
        config_io.load_run_config(tmp_path)


# --------------------------------------------------------------------------- #
# AC11 — migration sits OUTSIDE the read boundary
# --------------------------------------------------------------------------- #

def test_migration_only_ever_sees_a_dict(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        "orchestrator_pkg.legacy_migration._migrate_legacy_pipeline_if_needed",
        lambda _root, config: seen.append(config) or config,
    )
    for content in ("null", "[]", "123"):
        write(tmp_path, content)
        with pytest.raises(RunConfigUnreadable):
            config_io.read_run_config(tmp_path, migrate=True)
    assert seen == [], "migration was handed a non-object"


def test_migration_failure_is_not_relabelled_as_a_corrupt_config(tmp_path, monkeypatch):
    """A KeyError in our migration is OUR bug; calling it 'corrupt config' sends
    the operator to delete a good file."""
    write(tmp_path, json.dumps(real_config()))
    monkeypatch.setattr(
        "orchestrator_pkg.legacy_migration._migrate_legacy_pipeline_if_needed",
        raiser(KeyError("pipeline")),
    )
    with pytest.raises(KeyError):
        config_io.read_run_config(tmp_path, migrate=True)
