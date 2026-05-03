"""Tests for aggregate_changelog.py — focused on the MSYS path-conversion
linter introduced after the v0.15.0 release-prep near-miss.

Bug class: Git-Bash on Windows auto-converts a leading-slash argv
argument into ``C:/Program Files/Git/...`` before the receiving Python
script sees it. So a bullet text like ``/shipwright-adopt now scaffolds…``
gets persisted as ``C:/Program Files/Git/shipwright-adopt now
scaffolds…`` in the drop file. The aggregator was previously blind to
this and would happily publish the mangled bullet into ``CHANGELOG.md``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Aggregator imports the write-side helper at module load — make both
# available on sys.path the same way other shared/tests/ files do.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from tools.aggregate_changelog import aggregate  # noqa: E402
from tools.write_changelog_drop import write_changelog_drop  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Bare project root with a Keep-a-Changelog skeleton."""
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "All notable changes to this project will be documented in this file.\n\n"
        "## [Unreleased]\n\n"
        "## [0.0.1] - 2026-01-01\n\n"
        "### Added\n\n"
        "- Initial release\n",
        encoding="utf-8",
    )
    return tmp_path


_MANGLED = (
    "C:/Program Files/Git/shipwright-adopt now scaffolds "
    "<project_root>/.env.local with profile required_env_vars (ADR-021)."
)
_CLEAN = (
    "/shipwright-adopt now scaffolds <project_root>/.env.local with "
    "profile required_env_vars (ADR-021)."
)


# ---------------------------------------------------------------------------
# AC-1 — release-time linter detects mangled bullets, WARN by default
# ---------------------------------------------------------------------------

def test_aggregate_warns_on_mangled_bullet_default(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A drop file whose bullet starts with the Git-Bash mangle prefix
    triggers a stderr WARN naming the source drop file. Aggregation
    still proceeds (default = warn-only)."""
    write_changelog_drop(project, "iterate-2026-05-03-test", "Added", _MANGLED)
    result = aggregate(project, "1.0.0", release_date="2026-05-03")

    assert result["changelog_updated"] is True
    err = capsys.readouterr().err
    assert "MSYS" in err or "Git-Bash" in err or "mangled" in err.lower(), (
        f"Expected MSYS/Git-Bash mangling WARN on stderr, got: {err!r}"
    )
    # The WARN must point at the offending drop file so the operator
    # can find + edit it. Filename includes the run_id.
    assert "iterate-2026-05-03-test" in err


def test_aggregate_silent_on_clean_bullets(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bullets without the mangle prefix produce no MSYS warnings — only
    other unrelated warnings (e.g. legacy [Unreleased]) may appear."""
    write_changelog_drop(project, "iterate-2026-05-03-test", "Added", _CLEAN)
    aggregate(project, "1.0.0", release_date="2026-05-03")

    err = capsys.readouterr().err
    assert "MSYS" not in err
    assert "Git-Bash" not in err
    assert "mangled" not in err.lower()


# ---------------------------------------------------------------------------
# AC-2 — --strict elevates the WARN to a BLOCK (no aggregation, exit non-zero)
# ---------------------------------------------------------------------------

def test_aggregate_strict_blocks_on_mangled_bullet(project: Path) -> None:
    """In strict mode, a mangled bullet causes the aggregator to refuse
    the run: raises an aggregator error AND leaves the drop file in
    place + CHANGELOG.md untouched."""
    drop_path = write_changelog_drop(
        project, "iterate-2026-05-03-test", "Added", _MANGLED
    )
    pre_changelog = (project / "CHANGELOG.md").read_text(encoding="utf-8")

    from tools.aggregate_changelog import AggregatorError

    with pytest.raises(AggregatorError, match="(?i)msys|git-bash|mangled"):
        aggregate(project, "1.0.0", release_date="2026-05-03", strict=True)

    # Drop file still on disk — operator can fix and re-run.
    assert drop_path.exists(), "strict-mode block must NOT delete the drop file"
    # CHANGELOG.md unchanged — no partial write.
    assert (project / "CHANGELOG.md").read_text(encoding="utf-8") == pre_changelog


def test_aggregate_strict_passes_when_clean(project: Path) -> None:
    """Strict mode is a no-op on clean drop files — same outcome as default."""
    write_changelog_drop(project, "iterate-2026-05-03-test", "Added", _CLEAN)
    result = aggregate(project, "1.0.0", release_date="2026-05-03", strict=True)
    assert result["changelog_updated"] is True


# ---------------------------------------------------------------------------
# AC-3 — write-side defensive WARN at drop-write time
# ---------------------------------------------------------------------------

def test_write_changelog_drop_warns_on_mangled_bullet_at_write_time(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """write_changelog_drop emits a stderr WARN when the incoming bullet
    starts with the Git-Bash mangle prefix. It DOES NOT fail the write —
    by the time the script sees the argv, the user's intent can't be
    reliably recovered (legitimate paths under Git's install dir would
    be false-positives if we auto-rewrote)."""
    written = write_changelog_drop(
        project, "iterate-2026-05-03-test", "Added", _MANGLED
    )
    err = capsys.readouterr().err
    assert "MSYS" in err or "Git-Bash" in err or "mangled" in err.lower(), (
        f"Expected write-time WARN, got: {err!r}"
    )
    # Write must have succeeded — the bullet is preserved verbatim for
    # the operator to inspect later.
    assert written.exists()
    assert written.read_text(encoding="utf-8").strip() == _MANGLED.strip()


def test_write_changelog_drop_silent_on_clean_bullet(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No MSYS warning on a bullet that doesn't start with the mangle prefix."""
    write_changelog_drop(project, "iterate-2026-05-03-test", "Added", _CLEAN)
    err = capsys.readouterr().err
    assert "MSYS" not in err
    assert "Git-Bash" not in err
    assert "mangled" not in err.lower()


# ---------------------------------------------------------------------------
# AC-2 (CLI) — --strict surfaces as a CLI flag with the documented exit code
# ---------------------------------------------------------------------------

def test_aggregate_cli_strict_flag_exits_nonzero_on_mangled(
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI entry point exposes --strict; it returns non-zero on
    mangled bullets so release CI can fail-fast on the bug."""
    write_changelog_drop(project, "iterate-2026-05-03-test", "Added", _MANGLED)

    from tools.aggregate_changelog import main as agg_main

    rc = agg_main([
        "--project-root", str(project),
        "--version", "1.0.0",
        "--release-date", "2026-05-03",
        "--strict",
    ])
    assert rc != 0, "strict mode must exit non-zero on mangled drops"
    # Default (no --strict) still aggregates the same input — proves the
    # flag is the only thing that elevates WARN to BLOCK.
    rc2 = agg_main([
        "--project-root", str(project),
        "--version", "1.0.0",
        "--release-date", "2026-05-03",
    ])
    assert rc2 == 0, "default (warn-only) mode must still aggregate"
