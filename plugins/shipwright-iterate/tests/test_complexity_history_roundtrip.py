"""Round-trip + CLI tests for the history-calibrated complexity prior.

AC-5: the REAL shared writer (append_iterate_entry.py) feeds the plugin
reader — pins the path + field + sort contract across the plugin/shared
boundary without a runtime import dependency.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _complexity_test_helpers import (  # noqa: E402
    CLASSIFY_CLI,
    FALLTHROUGH_MSG,
    REPO_ROOT,
    seeded_root,
    write_entry,
)
from classify_complexity import classify  # noqa: E402
from complexity_history import (  # noqa: E402
    HISTORY_WINDOW,
    load_history_prior,
)


class TestRoundTripWithRealWriter:
    @pytest.fixture()
    def shared_writer(self):
        import importlib.util
        writer_path = (
            REPO_ROOT / "shared" / "scripts" / "tools"
            / "append_iterate_entry.py"
        )
        try:
            spec = importlib.util.spec_from_file_location(
                "append_iterate_entry_rt", writer_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except (ImportError, FileNotFoundError) as exc:  # pragma: no cover
            if os.environ.get("CI", "").lower() in ("true", "1"):
                pytest.fail(
                    "shared append_iterate_entry.py not importable in CI: "
                    f"{exc} — run from the monorepo root checkout"
                )
            pytest.skip(f"shared writer unavailable: {exc}")
        return mod

    def test_jumbled_writes_sorted_window_median(self, tmp_path, shared_writer):
        # 25 entries with sequential dates written in a jumbled but
        # deterministic order; the 5 oldest are trivial. The reader must
        # sort by (date, run_id) and take the last HISTORY_WINDOW=20:
        # 13 medium + 7 small → median medium.
        specs = []
        for i in range(25):
            cx = ("trivial" if i < 5 else "small" if i < 12 else "medium")
            specs.append((
                f"iterate-2026-05-{i + 1:02d}-rt-{i:03d}",
                f"2026-05-{i + 1:02d}T10:00:00Z",
                cx,
            ))
        jumbled = specs[12:] + specs[:5] + specs[5:12]
        for run_id, date, cx in jumbled:
            shared_writer.append_iterate_entry(tmp_path, {
                "run_id": run_id,
                "date": date,
                "type": "change",
                "complexity": cx,
                "branch": f"iterate/{run_id}",
                "tests_passed": True,
            })
        result = load_history_prior(tmp_path)
        assert result["prior"] == "medium"
        assert result["n"] == HISTORY_WINDOW
        classified = classify(FALLTHROUGH_MSG, project_root=tmp_path)
        assert classified["estimate"] == "medium"
        assert classified["signals"]["prior_source"] == "history"

    def test_real_field_entry_shape_parses(self, tmp_path, shared_writer):
        # Shape copied from an actual entry in the field (2026-06-10) —
        # guards against drift from the oldest supported real-world form.
        field_entry = {
            "run_id": "iterate-2026-06-10-triage-dedup-keep-last-append",
            "date": "2026-06-09T22:26:37.674867Z",
            "type": "change",
            "complexity": "small",
            "branch": "iterate/2026-06-10-triage-dedup-keep-last-append",
            "tests_passed": True,
            "change_type": "infra",
            "adr": "iterate-2026-06-10-triage-dedup-keep-last-append",
        }
        shared_writer.append_iterate_entry(tmp_path, field_entry)
        write_entry(tmp_path, "iterate-2026-06-11-a", "2026-06-11T00:00:00Z",
                    "small")
        write_entry(tmp_path, "iterate-2026-06-12-b", "2026-06-12T00:00:00Z",
                    "small")
        result = load_history_prior(tmp_path)
        assert result["prior"] == "small"
        assert result["n"] == 3


class TestStandaloneLoading:
    def test_spec_from_file_location_without_syspath_prep(self, tmp_path):
        # External-review finding: classify_complexity now needs its sibling
        # modules. shared/scripts/tools/tests/test_record_event.py loads the
        # file via spec_from_file_location with NO sys.path preparation —
        # the module's self-bootstrap must make sibling imports resolve.
        import importlib.util
        loaded = sys.modules.pop("classify_complexity", None)
        try:
            spec = importlib.util.spec_from_file_location(
                "classify_complexity_standalone", CLASSIFY_CLI)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            seeded_root(tmp_path, ["medium"] * 5)
            result = mod.classify(FALLTHROUGH_MSG, project_root=tmp_path)
            assert result["signals"]["prior_source"] == "history"
        finally:
            if loaded is not None:
                sys.modules["classify_complexity"] = loaded

    def test_sibling_modules_ship_together(self):
        lib = CLASSIFY_CLI.parent
        for sibling in ("complexity_history.py", "complexity_vocabulary.py"):
            assert (lib / sibling).is_file(), (
                f"{sibling} must be deployed alongside classify_complexity.py"
            )


class TestCli:
    def run_cli(self, *args):
        proc = subprocess.run(
            [sys.executable, str(CLASSIFY_CLI), *args],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    def test_project_root_flag_activates_prior(self, tmp_path):
        seeded_root(tmp_path, ["medium"] * 5)
        out = self.run_cli("--message", FALLTHROUGH_MSG,
                           "--project-root", str(tmp_path))
        assert out["estimate"] == "medium"
        assert out["signals"]["prior_source"] == "history"

    def test_without_flag_old_behaviour(self):
        out = self.run_cli("--message", FALLTHROUGH_MSG)
        assert out["estimate"] == "trivial"
        assert out["signals"]["prior_source"] == "default"
