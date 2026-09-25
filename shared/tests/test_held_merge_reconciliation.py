"""Unit tests for ``lib.held_merge_reconciliation`` (campaign-dag-scheduler
R5b round 7): the held-merge reconciliation pass extracted out of
campaign-mode.md step 4's inline bash/jq loop, per Tier-3 review's demand for
executable (not prose-only) coverage of this path. The CLI/subprocess
boundary (`_real_gh_query`, `_real_mark_merged`, `main`) lives in the sibling
`test_held_merge_reconciliation_cli.py`, split out when this file crossed
the 300-line guideline.
"""

from __future__ import annotations

from lib.held_merge_reconciliation import find_reconcilable_held, poll_for_merged_sha, reconcile


def _unit(unit_id: str, status: str, **extra) -> dict:
    row = {"id": unit_id, "status": status, "branch": f"iterate/{unit_id}", "worktree": None}
    row.update(extra)
    return row


class TestFindReconcilableHeld:
    def test_finds_drain_timeout_and_merge_confirmation_timeout(self):
        state = {"units": [
            _unit("A", "held", reason_code="drain_timeout"),
            _unit("B", "held", reason_code="merge_confirmation_timeout"),
            _unit("C", "held", reason_code="swept_never_started"),
            _unit("D", "held", reason_code="rebase_conflict"),
            _unit("E", "merged"),
        ]}
        assert {u["id"] for u in find_reconcilable_held(state)} == {"A", "B"}

    def test_empty_when_nothing_matches(self):
        state = {"units": [_unit("A", "merged"), _unit("B", "failed")]}
        assert find_reconcilable_held(state) == []


class TestPollForMergedSha:
    def test_returns_sha_on_first_successful_merged_query(self):
        def gh_query(branch, cwd):
            return {"state": "MERGED", "mergeCommit": {"oid": "abc123"}}

        sha = poll_for_merged_sha(
            gh_query, "iterate/A", "/wt", deadline_seconds=60,
            poll_interval_seconds=5, sleep_fn=lambda _s: None, time_fn=_counting_clock(),
        )
        assert sha == "abc123"

    def test_retries_a_gh_query_failure_within_the_same_window(self):
        """A `gh` failure (network, auth, `None`) must never be treated as
        proof the PR is still open -- it retries within the bound."""
        calls = {"n": 0}

        def gh_query(branch, cwd):
            calls["n"] += 1
            if calls["n"] < 3:
                return None
            return {"state": "MERGED", "mergeCommit": {"oid": "def456"}}

        sha = poll_for_merged_sha(
            gh_query, "iterate/A", "/wt", deadline_seconds=60,
            poll_interval_seconds=5, sleep_fn=lambda _s: None, time_fn=_counting_clock(),
        )
        assert sha == "def456"
        assert calls["n"] == 3

    def test_merged_state_with_empty_sha_keeps_polling(self):
        """The merge event and the SHA becoming visible are not atomic."""
        calls = {"n": 0}

        def gh_query(branch, cwd):
            calls["n"] += 1
            if calls["n"] < 2:
                return {"state": "MERGED", "mergeCommit": {"oid": ""}}
            return {"state": "MERGED", "mergeCommit": {"oid": "ghi789"}}

        sha = poll_for_merged_sha(
            gh_query, "iterate/A", "/wt", deadline_seconds=60,
            poll_interval_seconds=5, sleep_fn=lambda _s: None, time_fn=_counting_clock(),
        )
        assert sha == "ghi789"

    def test_merged_state_with_null_merge_commit_keeps_polling(self):
        """GitHub returns the `mergeCommit` KEY with an explicit JSON `null`
        (not an absent key, not `{"oid": ""}`) while MERGED but the SHA has
        not become visible yet -- the same race `test_merged_state_with_
        empty_sha_keeps_polling` covers for the `{"oid": ""}` shape. Tier-3
        review, R5b round 10, blocking: `result.get("mergeCommit", {})` only
        substitutes its default for an ABSENT key, so this shape raised
        `AttributeError: 'NoneType' object has no attribute 'get'` instead of
        polling through it as the docstring above promises."""
        calls = {"n": 0}

        def gh_query(branch, cwd):
            calls["n"] += 1
            if calls["n"] < 2:
                return {"state": "MERGED", "mergeCommit": None}
            return {"state": "MERGED", "mergeCommit": {"oid": "jkl012"}}

        sha = poll_for_merged_sha(
            gh_query, "iterate/A", "/wt", deadline_seconds=60,
            poll_interval_seconds=5, sleep_fn=lambda _s: None, time_fn=_counting_clock(),
        )
        assert sha == "jkl012"

    def test_exhausting_the_window_returns_none(self):
        """A genuinely-still-open PR (or a `gh` query that never succeeds)
        must leave the row exactly as recorded, never block finalize."""
        def gh_query(branch, cwd):
            return {"state": "OPEN", "mergeCommit": None}

        sha = poll_for_merged_sha(
            gh_query, "iterate/A", "/wt", deadline_seconds=20,
            poll_interval_seconds=5, sleep_fn=lambda _s: None, time_fn=_counting_clock(step=5),
        )
        assert sha is None


def _counting_clock(step: float = 1.0):
    state = {"t": 0.0}

    def clock():
        state["t"] += step
        return state["t"]

    return clock


class TestReconcile:
    def test_corrects_a_genuinely_merged_held_unit(self):
        state = {"units": [_unit("A", "held", reason_code="drain_timeout")]}
        marked = []

        def gh_query(branch, cwd):
            return {"state": "MERGED", "mergeCommit": {"oid": "sha-a"}}

        def mark_merged(unit_id, merged_sha):
            marked.append((unit_id, merged_sha))
            return True

        corrected = reconcile(
            state, project_root="/proj", gh_query_fn=gh_query, mark_merged_fn=mark_merged,
            sleep_fn=lambda _s: None, time_fn=_counting_clock(),
        )
        assert corrected == [{"id": "A", "merged_sha": "sha-a"}]
        assert marked == [("A", "sha-a")]

    def test_leaves_a_still_open_unit_untouched(self):
        state = {"units": [_unit("A", "held", reason_code="drain_timeout")]}
        marked = []

        def gh_query(branch, cwd):
            return {"state": "OPEN", "mergeCommit": None}

        def mark_merged(unit_id, merged_sha):
            marked.append((unit_id, merged_sha))
            return True

        corrected = reconcile(
            state, project_root="/proj", gh_query_fn=gh_query, mark_merged_fn=mark_merged,
            deadline_seconds=10, poll_interval_seconds=5,
            sleep_fn=lambda _s: None, time_fn=_counting_clock(step=5),
        )
        assert corrected == []
        assert marked == []

    def test_never_touches_a_unit_with_an_unrelated_reason_code(self):
        state = {"units": [_unit("A", "held", reason_code="rebase_conflict")]}
        queried = {"n": 0}

        def gh_query(branch, cwd):
            queried["n"] += 1
            return {"state": "MERGED", "mergeCommit": {"oid": "sha-a"}}

        corrected = reconcile(
            state, project_root="/proj", gh_query_fn=gh_query, mark_merged_fn=lambda *_: True,
            sleep_fn=lambda _s: None, time_fn=_counting_clock(),
        )
        assert corrected == []
        assert queried["n"] == 0, "a unit outside the reconcilable reason codes must never be queried at all"

    def test_falls_back_to_project_root_when_the_units_own_worktree_is_gone(self, tmp_path):
        state = {"units": [_unit("A", "held", reason_code="drain_timeout", worktree=str(tmp_path / "gone"))]}
        seen_cwd = {}

        def gh_query(branch, cwd):
            seen_cwd["cwd"] = cwd
            return {"state": "MERGED", "mergeCommit": {"oid": "sha-a"}}

        reconcile(
            state, project_root="/proj", gh_query_fn=gh_query, mark_merged_fn=lambda *_: True,
            sleep_fn=lambda _s: None, time_fn=_counting_clock(),
        )
        assert seen_cwd["cwd"] == "/proj"

    def test_a_mark_merged_failure_is_not_reported_as_corrected(self):
        state = {"units": [_unit("A", "held", reason_code="drain_timeout")]}

        def gh_query(branch, cwd):
            return {"state": "MERGED", "mergeCommit": {"oid": "sha-a"}}

        corrected = reconcile(
            state, project_root="/proj", gh_query_fn=gh_query, mark_merged_fn=lambda *_: False,
            sleep_fn=lambda _s: None, time_fn=_counting_clock(),
        )
        assert corrected == []

    def test_covers_both_units_independently(self):
        state = {"units": [
            _unit("A", "held", reason_code="drain_timeout"),
            _unit("B", "held", reason_code="merge_confirmation_timeout"),
        ]}
        responses = {"A": "sha-a", "B": "sha-b"}

        def gh_query(branch, cwd):
            unit_id = branch.rsplit("/", 1)[-1]
            return {"state": "MERGED", "mergeCommit": {"oid": responses[unit_id]}}

        corrected = reconcile(
            state, project_root="/proj", gh_query_fn=gh_query, mark_merged_fn=lambda *_: True,
            sleep_fn=lambda _s: None, time_fn=_counting_clock(),
        )
        assert {(r["id"], r["merged_sha"]) for r in corrected} == {("A", "sha-a"), ("B", "sha-b")}
