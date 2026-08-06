"""Shared fixtures for the corrupt-run-config suites.

Split out of ``test_runconfig_corrupt_fail_closed.py`` so neither suite exceeds
the 300-LOC file budget. Uniquely named on purpose: plain names like ``shapes``
or ``helpers`` collide across plugin test roots, which is exactly the failure
ADR-044 records (Python caches whichever package loads first, and ``sys.path``
order cannot fix it).

The two dicts below ARE the Boundary Probe. The round trip they enumerate is
"file content -> the reader's answer", exhaustively over the byte-shapes a JSON
file can hold, because every door in this defect was opened by a shape nobody
had written down:

    truncated / ""      -> JSONDecodeError, warned              (the reported bug)
    null / []           -> parses fine, NO warning at all       (silent)
    a file holding "{}" -> present but falsy, bootstrapped over (truthiness)
    standalone: "false" -> a truthy STRING read as standalone   (semantic)
"""
import json
from pathlib import Path

_CONFIG_NAME = "shipwright_run_config.json"

#: A distinctive marker used to prove no file content reaches a rendered message.
#: Deliberately not shaped like a credential — this is a canary, not a secret.
CANARY_MARKER = "zz-canary-e3b0c44298fc1c14"


def real_config() -> dict:
    """A driven, NOT-standalone run carrying state that is worth losing."""
    return {
        "schemaVersion": 2,
        "runId": "run-real-001",
        "mode": "single_session",
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
        "phase_tasks": [{"phaseTaskId": "pt-1", "phase": "project", "status": "completed"}],
        "completed_phase_task_ids": ["pt-1"],
        "status": "in_progress",
        "completed_steps": ["project", "design"],
        "current_step": "plan",
        "standalone": False,
        "validation_overrides": [{"step": "design", "reason": "prior override", "waived": True}],
        "phase_history": {},
    }


def truncated() -> str:
    """The reported shape: a config cut in half mid-write."""
    raw = json.dumps(real_config(), indent=2)
    return raw[: len(raw) // 2]


def write(root: Path, text: str) -> Path:
    path = root / _CONFIG_NAME
    path.write_text(text, encoding="utf-8")
    return path


def raiser(exc: BaseException):
    """A ``durable_read_text`` stand-in that fails a given way."""
    def _boom(*_args, **_kwargs):
        raise exc
    return _boom


#: Shapes that must be refused by the strict reader.
UNUSABLE_CONTENT = {
    "empty": "",
    "truncated": truncated(),
    "not_json": "{oops",
    "json_null": "null",
    "json_empty_list": "[]",
    "json_list": "[1, 2]",
    "json_number": "123",
    "json_string": '"hello"',
}

#: Shapes that are a usable config — including the empty object, which is a
#: PRESENT config and must never be mistaken for an absent one.
USABLE_CONTENT = {
    "empty_object": "{}",
    "standalone_true": '{"standalone": true}',
    "standalone_false": '{"standalone": false}',
    "no_standalone_key": '{"pipeline": ["plan"]}',
}
