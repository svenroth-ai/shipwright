"""A review-record row that satisfies the closure rules, for tests about something else.

Since the review-record gate runs at every complexity, a record passes only if
``self`` is completed with evidence and every ``not_run`` / ``not_applicable``
row carries a closed-vocabulary ``reason_code``
(``tools/verifiers/review_record_closure.py``). Tests whose subject is the
code-review floor, the model-tier note or the transport field build every OTHER
row through :func:`background_row`, so a failure isolates their own subject
rather than tripping the closure rules first.
"""

from __future__ import annotations

from lib.review_record_core import make_entry
from lib.review_record_schema import STATUS_COMPLETED, STATUS_NOT_RUN

#: A code that is legal at every complexity above trivial and plausible for any type.
BACKGROUND_CODE = "complexity-below-threshold"


def background_row(review_type: str, disposition: str, *, status: str = STATUS_NOT_RUN,
                   reason_code: str = BACKGROUND_CODE) -> dict:
    """``self`` completed via the self-review adapter; any other type closed with a code."""
    if review_type == "self":
        return make_entry("self", STATUS_COMPLETED, recorded_by="self-review")
    return {**make_entry(review_type, status, disposition=disposition), "reason_code": reason_code}
