"""Shared helpers for the event-reader tests (S2): drop files and the unsplit/split fixture pair."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from _events_split import split_log  # noqa: E402

from lib.events_log import DROPS_DIR  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "events_layout"


def _line(**kw) -> str:
    return json.dumps(kw, separators=(",", ":"))


def _write(path: Path, *lines: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _drop(root: Path, key: str, *lines: str, nonce: str = "00000001") -> Path:
    return _write(root / DROPS_DIR / f"{key}--aaaaaaaa--{nonce}.jsonl", *lines)


def _unsplit_project(tmp_path: Path) -> Path:
    root = tmp_path / "unsplit"
    root.mkdir()
    shutil.copyfile(FIX / "unsplit.jsonl", root / "shipwright_events.jsonl")
    return root


def _split_project(tmp_path: Path) -> Path:
    root = tmp_path / "split"
    root.mkdir()
    split_log(FIX / "unsplit.jsonl", root)
    return root
