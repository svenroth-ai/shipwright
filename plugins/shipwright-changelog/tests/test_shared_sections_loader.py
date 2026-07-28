"""The loader that reaches the shared section predicates.

`changelog_sections` lives at `shared/scripts/` top level (ADR-045) so this
plugin's writer and the release-time aggregator share one implementation. It is
loaded BY PATH under a private module name rather than off `sys.path`, because
`shared/scripts` also contains a `lib/` package and putting that ahead of this
plugin's own `scripts/lib` is the collision ADR-045 exists to prevent.

These tests cover the arms that only fire when something is wrong, and which
are therefore the easiest to get subtly wrong: `ensure_shared_cache` is
fail-open, so an install with a missing or stale `shared/` really does reach
this code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lib import _shared_sections


@pytest.fixture(autouse=True)
def _clear_module_cache():
    """Each test starts from an unloaded state and leaves one behind."""
    sys.modules.pop(_shared_sections._PRIVATE_NAME, None)
    yield
    sys.modules.pop(_shared_sections._PRIVATE_NAME, None)


def test_loads_the_shared_module_and_memoises_it() -> None:
    first = _shared_sections.load_changelog_sections()
    assert Path(first.__file__).name == "changelog_sections.py"
    assert Path(first.__file__).parent.name == "scripts"
    # Not under `lib/` — that placement is the whole point of ADR-045.
    assert Path(first.__file__).parent.name != "lib"

    assert _shared_sections.load_changelog_sections() is first, "must memoise"


def test_missing_shared_raises_an_actionable_import_error(monkeypatch) -> None:
    """`spec_from_file_location` picks a loader by SUFFIX and never stats the
    path, so for a `.py` location it always returns a spec with a working
    loader. Testing `spec is None` therefore leaves that arm dead and the
    operator gets a bare `FileNotFoundError` from `exec_module` instead — with
    no mention of what to do about it."""
    monkeypatch.setattr(
        _shared_sections,
        "_shared_module_path",
        lambda: Path("nonexistent") / "shared" / "scripts" / "changelog_sections.py",
    )

    with pytest.raises(ImportError) as excinfo:
        _shared_sections.load_changelog_sections()

    message = str(excinfo.value)
    assert "changelog_sections.py" in message, "name the file that is missing"
    assert "ensure_shared_cache" in message, "name the hook that restores it"
    assert "update-marketplace" in message, "and the dev-checkout remedy"


def test_a_failed_load_does_not_leave_a_broken_module_registered(
    monkeypatch, tmp_path: Path
) -> None:
    """Registering in `sys.modules` before `exec_module` is correct — a module
    that resolves its own name while executing needs it. Not UNregistering on
    failure is not: the memoisation fast path would hand out the
    half-initialised object for the rest of the process, and the real error
    would resurface far away as a missing attribute."""
    broken = tmp_path / "changelog_sections.py"
    broken.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    monkeypatch.setattr(_shared_sections, "_shared_module_path", lambda: broken)

    with pytest.raises(RuntimeError, match="boom"):
        _shared_sections.load_changelog_sections()

    assert _shared_sections._PRIVATE_NAME not in sys.modules, (
        "a failed load must not poison every later call in this process"
    )


def test_the_writer_only_needs_the_shared_module_when_it_splices() -> None:
    """The predicates are resolved inside `update_changelog`, not at import.

    Binding them at module scope made a missing or stale `shared/` fail the
    whole `lib.changelog` import, taking down `categorize_commits` and
    `generate_entry` — which never touch the predicates. `ensure_shared_cache`
    re-mirrors `shared/` only when its sentinel file is absent, so a cached
    copy predating this module is a reachable state; it must break only the
    splice.
    """
    from lib import changelog

    for name in ("entry_version", "insertion_index", "section_end", "section_starts"):
        assert not hasattr(changelog, name), (
            f"{name} is bound at module scope; a missing shared/ would then "
            "break the entire lib.changelog import"
        )

    # The functions that do not need the predicates keep working regardless.
    sections = changelog.categorize_commits(
        [{"type": "fix", "scope": "api", "description": "x", "breaking": False}]
    )
    assert "Fixed" in sections
    assert "## [1.0.0]" in changelog.generate_entry("1.0.0", sections, "2026-04-23")
