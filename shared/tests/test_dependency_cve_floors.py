"""Anti-regression floors for dependencies bumped to remediate a known CVE.

When we root-remediate a vulnerable transitive dependency by bumping it in a
lockfile, nothing structural stops a later ``uv lock`` regenerate (or a
resolver change) from quietly resolving back below the fixed version. The CI
security gate does not catch it either: ``.github/workflows/security.yml``
blocks only on *critical* findings, and these remediations are *high*.

So each remediated dependency gets a floor here — the bump becomes mechanical
discipline rather than a convention someone has to remember. Sibling guardrail
to ``test_trivyignore_register.py``: that one polices the risks we *accept*,
this one polices the ones we *fixed*.

Remove a row when the floor stops being meaningful (e.g. the package leaves
the tree, or the whole ecosystem has long since moved past it).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# (lockfile, package, minimum version, CVEs remediated, why it matters here)
CVE_FLOORS = [
    pytest.param(
        "plugins/shipwright-plan/uv.lock",
        "pyasn1",
        (0, 6, 4),
        "CVE-2026-59885 / CVE-2026-59886",
        "quadratic OID decode + unbounded REAL float conversion (DoS); "
        "reaches us via google-genai -> google-auth -> pyasn1-modules",
        id="pyasn1-plan",
    ),
]


def _parse_version(raw: str) -> tuple[int, ...]:
    """Parse a simple dotted release version into a comparable tuple.

    Trailing pre-release/local segments are dropped — a floor is about the
    release number, and comparing ``0.6.4`` against ``0.6.4rc1`` is not a
    distinction any row here needs to make.
    """
    parts: list[int] = []
    for chunk in raw.split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _locked_version(lockfile: Path, package: str) -> str | None:
    """Return the version `package` is pinned to in a uv lockfile, if present."""
    data = tomllib.loads(lockfile.read_text(encoding="utf-8"))
    for entry in data.get("package", []):
        if entry.get("name") == package:
            return entry.get("version")
    return None


@pytest.mark.parametrize("lockfile, package, floor, cves, why", CVE_FLOORS)
def test_remediated_dependency_stays_at_or_above_its_floor(
    lockfile: str, package: str, floor: tuple[int, ...], cves: str, why: str
):
    path = REPO_ROOT / lockfile
    assert path.is_file(), f"{lockfile} is missing — update or drop this floor"

    locked = _locked_version(path, package)
    assert locked is not None, (
        f"{package} is no longer in {lockfile}. If it genuinely left the "
        f"dependency tree, drop this row; do not silently ignore it."
    )

    floor_str = ".".join(str(n) for n in floor)
    assert _parse_version(locked) >= floor, (
        f"{package} in {lockfile} resolved back to {locked}, below the "
        f"{floor_str} floor that remediates {cves}.\n"
        f"Why this floor exists: {why}.\n"
        f"Fix: uv lock --directory {Path(lockfile).parent} "
        f"--upgrade-package {package}"
    )


def test_floor_comparison_rejects_a_downgrade():
    # A guard that never rejects is worthless — pin that it catches the case
    # it exists for (pyasn1 0.6.3, the version this iterate bumped away from).
    assert _parse_version("0.6.3") < (0, 6, 4), "must reject the vulnerable version"
    assert _parse_version("0.6.4") >= (0, 6, 4), "must accept the remediated version"
    assert _parse_version("0.7.0") >= (0, 6, 4), "must accept a later minor"
    assert _parse_version("1.0.0") >= (0, 6, 4), "must accept a later major"


def test_every_floor_row_points_at_a_real_lockfile():
    # Reverse drift protection: a renamed/removed lockfile must fail loudly
    # here rather than turning the floor into a silent no-op.
    for param in CVE_FLOORS:
        lockfile = param.values[0]
        assert (REPO_ROOT / lockfile).is_file(), f"floor references missing {lockfile}"
