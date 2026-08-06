"""The run-config error contract: what "this file exists but I cannot use it" is.

Its own module because five modules import it (``config_io`` raises it,
``step_planning`` / ``step_config_access`` / ``cli_update_step`` / ``router`` /
``config_factory`` handle it) and because ``config_io`` sits at its 300-LOC
budget. Re-exported from ``config_io`` so callers keep one import site.

The defect it exists to make impossible is recorded in
``.shipwright/planning/iterate/iterate-2026-08-05-standalone-flag-corrupt-config.md``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["MAX_DETAIL_CHARS", "RunConfigUnreadable"]


# Cap on the text carried into a user-facing message. Detail is built from the
# exception TYPE and MESSAGE only — never file content — and bounded so a
# pathological parser message cannot flood a terminal or a log.
MAX_DETAIL_CHARS = 300

# What kind of unusable. Advice differs per category — that is the point:
# "delete it and re-run" is right for damaged CONTENT and actively wrong for a
# permissions fault, where the file is fine.
# The content arms name the copy-first step deliberately: write-config REPLACES
# this file whether or not it was deleted first, so "delete it and re-run" alone
# read as though the bytes were safe until the operator chose otherwise.
_RECREATE = "Copy it aside first if you want to keep it - re-running REPLACES it."
_ADVICE = {
    "parse": f"Repair the file, or re-run /shipwright-run to recreate it. {_RECREATE}",
    "shape": f"Repair the file, or re-run /shipwright-run to recreate it. {_RECREATE}",
    "decode": (
        "The file is not valid UTF-8. Repair the encoding, or re-run "
        f"/shipwright-run to recreate it. {_RECREATE}"
    ),
    "io": "Check the file's permissions and that the path is a file, then retry.",
}


class RunConfigUnreadable(RuntimeError):
    """The run config EXISTS but cannot be used as a config.

    Distinct from an ABSENT config, a valid first-run state that stays
    ``({}, present=False)``. Conflating the two is the defect this type makes
    impossible: the v1 step-advance path read "no config" out of an unusable one,
    silently demoted a driven run to standalone — switching off the phase gate,
    the ``--force`` reason requirement and the ``validation_overrides[]`` record
    together — then overwrote the file.

    ``category``: ``parse`` / ``shape`` / ``decode`` / ``io``, each with the
    advice that applies to it.
    """

    def __init__(
        self, path: Path, detail: str, category: str,
        *, original: BaseException | None = None,
    ) -> None:
        self.path = path
        self.detail = detail[:MAX_DETAIL_CHARS]
        self.category = category
        # Held EXPLICITLY, not read back off ``__cause__``: the tolerant reader
        # re-raises this for decode/io, and depending on every raise site
        # remembering ``from exc`` would turn one that forgot into a TypeError
        # inside the display surfaces the two-reader split keeps alive.
        self.original = original
        # Initialise the base so a bare ``str(exc)`` still says something.
        # ASCII ONLY: printed to a console, which on Windows is cp1252, where an
        # em-dash raises UnicodeEncodeError while rendering an ERROR — pinned by
        # test_message_is_encodable_on_a_cp1252_console. Built from the
        # ALREADY-BOUNDED fields so one cap governs all three.
        super().__init__(
            f"{path.name} cannot be read: {self.detail}\n"
            f"  This run cannot continue safely. The file recording which phases\n"
            f"  completed, and whether a gate was overridden, is unusable.\n"
            f"  {_ADVICE.get(category, '')}\n"
            f"  Path: {self.bounded_path}"
        )

    @property
    def bounded_path(self) -> str:
        return str(self.path)[:MAX_DETAIL_CHARS]

    def payload(self) -> dict[str, Any]:
        """The bounded, content-free diagnostic both the CLI and the library
        blocked-result render. One formatter, so a consumer that serialises the
        library result itself cannot become the leak this bounding closes."""
        return {
            "ok": False,
            "reason": "config_unreadable",
            "category": self.category,
            "detail": self.detail,
            "path": self.bounded_path,
            "message": str(self),
        }
