"""F0 evidence retention — keep every unit's OWN JUnit report on ANY outcome,
not only on failure (iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC2).

Split out of `run_test_suite.py` to keep that module inside its bloat-gate
budget (`shipwright_bloat_baseline.json`, ADR-123 — zero headroom, same
reasoning `suite_units.py`'s own docstring already gives for its own split).

No second pytest pass is introduced anywhere: this module only relocates
reports F0 already produced. Reports and the side-manifest are written to a
per-run PENDING directory and atomically published (renamed into place) only
once every unit has a final outcome — an interrupted or concurrent F0 run
must never leave a partially-written side-manifest readable by
`stage_f0_evidence.py` (AC3). Retention failure is never allowed to fail an
otherwise-green F0 run: every entry point here degrades to a logged warning,
mirroring `run_test_suite._retain_attempt_evidence`'s existing swallow-and-
report pattern for the same reason.

Retry-supersedes-initial (AC2) falls out for free: :meth:`Retention.record`
is called once per attempt (initial, then retry if one ran) and always writes
to the SAME per-unit destination filename, so a retry's report silently
overwrites the initial attempt's — the authoritative attempt is whichever one
was recorded last, which is always the retry when one happened.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.lib.repo_root import resolve_main_repo_root  # noqa: E402
from scripts.lib.suite_root_plan import base_for_root  # noqa: E402
from scripts.tools.suite_units import Unit, cov_label  # noqa: E402

SCHEMA_VERSION = 1
#: Published run directories kept on local disk; older ones are pruned on publish.
RETAINED_RUNS = 5


def _key(value: str, length: int) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def retention_root(project_root: Path) -> Path:
    """The durable store's root — the MAIN repo tree, not a worktree (a worktree
    run's retained evidence must survive the worktree being removed after merge,
    same reasoning as `write_attempt_evidence`'s own diagnostics store)."""
    durable_root = resolve_main_repo_root(project_root) or Path(project_root)
    return durable_root / ".shipwright" / "runs" / "f0-evidence"


def unit_base(project_root: Path, unit: Unit) -> str:
    """The JUnit id-rebase base for one discovered unit — the SAME rule ci.yml's
    AC4 step uses for its expected root/base set, via the one shared function
    (`base_for_root`) both consult."""
    root = Path(project_root) / unit.cwd / unit.target
    return base_for_root(Path(project_root), root)


@dataclass
class Retention:
    """One F0 run's in-progress retention state. Publish once, at the end."""

    project_root: Path
    run_id: str
    _pending_dir: Path = field(init=False)
    _units: dict[str, dict] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._pending_dir = (
            retention_root(self.project_root) / "pending"
            / f"f0-{_key(self.run_id, 12)}-{uuid4().hex[:8]}"
        )

    def record(self, unit: Unit, report_path: Path, outcome: str) -> None:
        """Record (or supersede, on a retry) one unit's attempt. Never raises —
        a retention failure must not turn a green F0 run into a false STOP."""
        try:
            entry = {"base": unit_base(self.project_root, unit),
                     "report_path": None, "outcome": outcome}
            if report_path.is_file():
                dest = self._pending_dir / "reports" / f"{cov_label(unit.id)}.xml"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(report_path, dest)
                entry["report_path"] = f"reports/{cov_label(unit.id)}.xml"
            self._units[unit.id] = entry
        except OSError as exc:
            warnings.warn(f"F0 retention: could not record {unit.id!r}: {exc}", stacklevel=2)

    def publish(self) -> Path | None:
        """Write the side-manifest and atomically rename into `published/`.

        Returns the published directory, or None if nothing was ever recorded
        or publishing failed — both advisory, never raised.
        """
        if not self._units:
            return None
        try:
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "published_at": datetime.now(timezone.utc).isoformat(),
                "units": [
                    {"unit_id": unit_id, **entry}
                    for unit_id, entry in sorted(self._units.items())
                ],
            }
            (self._pending_dir).mkdir(parents=True, exist_ok=True)
            (self._pending_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            published_dir = retention_root(self.project_root) / "published" / self._pending_dir.name
            published_dir.parent.mkdir(parents=True, exist_ok=True)
            self._pending_dir.rename(published_dir)
            _prune_old_runs(published_dir.parent)
            return published_dir
        except OSError as exc:
            warnings.warn(f"F0 retention: could not publish run {self.run_id!r}: {exc}",
                          stacklevel=2)
            return None


def _prune_old_runs(published_root: Path) -> None:
    """Keep the newest RETAINED_RUNS published runs; best-effort delete the rest.

    Local disk hygiene, not durable evidence — a stale dir this misses is
    harmless, so a failure to remove one (a held-open file, e.g.) is swallowed
    rather than surfaced.
    """
    try:
        runs = sorted(
            (p for p in published_root.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
    except OSError:
        return
    for stale in runs[RETAINED_RUNS:]:
        shutil.rmtree(stale, ignore_errors=True)
