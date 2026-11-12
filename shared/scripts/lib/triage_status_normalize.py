"""An `append` whose `status` is missing, null or unknown reads as `triage`.

The append-only log is also written by hand and by older producers. An append
without a usable `status` is a malformed *item*, not a damaged *file*: the bytes
decode fine, so it must neither be dropped nor reported as corruption
(`corruption` is the WebUI contract for undecodable bytes). The reader gives it
the one status every new item starts with and says so on stderr, once per id,
so the operator can see the record needs a look.

Known limits: any unknown word reads as `triage`, including closed-sounding ones
("done", "closed"); and the warning is printed on every read for as long as the
append line exists, because the log is append-only and no supported action can
rewrite it (a later status event changes the resolved status, not the line).

Pure: takes the valid-status tuple as a parameter and never imports `triage`
(import-cycle rule of `lib/triage_integrity.py`).
"""

from __future__ import annotations

import sys

__all__ = ["DEFAULT_STATUS", "initial_record"]

DEFAULT_STATUS = "triage"

#: Ids already announced in this process; one malformed append is warned once
#: even though a single CLI run reads the store several times. Once per LOADED
#: MODULE and per id (not per store), the same caveat as `triage_integrity._REPORTED`.
_WARNED: set[str] = set()


def initial_record(raw: dict, statuses) -> dict:
    """The base record for an `append` line: `raw` minus the internal `event`
    key, with a missing/null/unknown `status` resolved to `triage` (warning)."""
    item = {k: v for k, v in raw.items() if k != "event"}
    status = item.get("status")
    if isinstance(status, str) and status in statuses:
        return item
    item["status"] = DEFAULT_STATUS
    item_id = str(item.get("id"))  # a record without an id is warned once as "None"
    if item_id not in _WARNED:
        if sys.stderr is not None:  # pythonw / detached processes have none
            sys.stderr.write(
                f"triage: integrity warning - append {ascii(item_id)} has "
                f"{'no' if 'status' not in raw else 'an unusable'} status "
                f"({ascii(status)}); read as 'triage'.\n"
            )
        _WARNED.add(item_id)
    return item
