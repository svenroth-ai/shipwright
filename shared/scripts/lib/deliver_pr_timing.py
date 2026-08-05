"""``deliver_pr.py``'s timing instrumentation — split out to keep that file
under the 300-line guideline. All three helpers here are best-effort,
additive, and never alter the ladder's own decisions; see
``iterate-timings.md`` for the design contract.
"""

from __future__ import annotations

from lib.iterate_timings import span as timing_span


def instrument_watch(watch, project_root, run_id):
    """Wrap the injected ``watch`` callable so rung 2's wait-for-the-host-merge
    call boundary records a ``ci_wait`` span."""
    def _watched(*args, **kwargs):
        with timing_span(project_root, run_id, name="ci_wait", parent="delivery_wait") as extra:
            verdict = watch(*args, **kwargs)
            if extra is not None and isinstance(verdict, dict):
                extra["rung"] = "host_watch"
                if "timed_out" in verdict:
                    extra["timed_out"] = bool(verdict["timed_out"])
                observed = verdict.get("checks_observed")
                # bool is an int subclass in Python - an unguarded isinstance
                # check would let checks_observed=True through, and the
                # closed-vocabulary validator's bool-vs-int distinction would
                # then reject the WHOLE span write (external code review),
                # losing the ci_wait span entirely rather than just the field.
                if isinstance(observed, int) and not isinstance(observed, bool):
                    extra["checks_observed"] = observed
        return verdict
    return _watched


def timed_self_merge_call(project_root, run_id, call):
    """Run rung 3's ``self_merge()`` ``call`` (a zero-arg closure) under a
    ``ci_wait`` span — the wait-for-checks-green portion of self-merging."""
    with timing_span(project_root, run_id, name="ci_wait", parent="delivery_wait") as extra:
        result = call()
        if extra is not None:
            extra["rung"] = "self_merge"
    return result


def delivery_root_span(project_root, run_id):
    """The top-level ``delivery`` span ``deliver()`` self-records so it never
    depends on the SKILL having marked entry into delivery beforehand."""
    return timing_span(project_root, run_id, name="delivery", parent=None)


def delivery_wait_span(project_root, run_id):
    return timing_span(project_root, run_id, name="delivery_wait", parent="delivery")
