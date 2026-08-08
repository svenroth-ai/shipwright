"""Retention keeps explicitly pinned F5c summaries reachable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.iterate_entry import (
    MIGRATION_STATE_KEY,
    RUN_CONFIG_NAME,
    entry_file_for,
    iterates_dir,
)
from shared.tests._iterate_entry_helpers import append_iterate_entry
from tools.append_iterate_entry import IterateAppendError


def _entry(run_id: str, date: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "date": date,
        "type": "bug",
        "complexity": "small",
        "branch": "iterate/test",
        "spec": None,
        "tests_passed": True,
        "adr": None,
    }


def test_retention_keeps_configured_pins_beyond_the_unpinned_window(
    tmp_path: Path,
) -> None:
    pinned = "iterate-2026-01-01-recovered"
    directory = iterates_dir(tmp_path)
    directory.mkdir(parents=True)
    (tmp_path / RUN_CONFIG_NAME).write_text(
        json.dumps(
            {
                "iterate_history": [],
                MIGRATION_STATE_KEY: "complete",
                "iterate_retention_pins": [pinned],
            }
        ),
        encoding="utf-8",
    )
    for run_id, date in (
        (pinned, "2026-01-01T00:00:00Z"),
        ("iterate-2026-01-02-unpinned", "2026-01-02T00:00:00Z"),
        ("iterate-2026-01-03-unpinned", "2026-01-03T00:00:00Z"),
    ):
        entry_file_for(tmp_path, run_id).write_text(
            json.dumps(_entry(run_id, date)), encoding="utf-8"
        )

    append_iterate_entry(
        tmp_path,
        _entry("iterate-2026-01-04-current", "2026-01-04T00:00:00Z"),
        retention=2,
    )

    assert entry_file_for(tmp_path, pinned).is_file()
    assert not entry_file_for(tmp_path, "iterate-2026-01-02-unpinned").exists()
    assert entry_file_for(tmp_path, "iterate-2026-01-03-unpinned").is_file()
    assert entry_file_for(tmp_path, "iterate-2026-01-04-current").is_file()

@pytest.mark.parametrize(
    "pins",
    [
        "iterate-2026-01-01-string",
        None,
        ["iterate-2026-01-01-ok", 3],
        ["duplicate", "duplicate"],
    ],
)
def test_malformed_retention_pins_fail_before_retention(tmp_path: Path, pins: object) -> None:
    iterates_dir(tmp_path).mkdir(parents=True)
    (tmp_path / RUN_CONFIG_NAME).write_text(
        json.dumps({"iterate_history": [], MIGRATION_STATE_KEY: "complete", "iterate_retention_pins": pins}),
        encoding="utf-8",
    )

    with pytest.raises(IterateAppendError, match="iterate_retention_pins"):
        append_iterate_entry(tmp_path, _entry("iterate-2026-01-04-current", "2026-01-04T00:00:00Z"))


def test_retention_pin_schema_requires_unique_non_empty_strings() -> None:
    schema_path = Path(__file__).parents[2] / "shared/schemas/run_config.v2.schema.json"
    pins = json.loads(schema_path.read_text(encoding="utf-8"))["properties"]["iterate_retention_pins"]
    assert pins["type"] == "array"
    assert pins["uniqueItems"] is True
    assert pins["items"] == {"type": "string", "minLength": 1}
